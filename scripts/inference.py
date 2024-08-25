from typing import Optional
import argparse
from dataclasses import dataclass, asdict


@dataclass
class CFG:
    output_filepath: str = 'submission.json'
    # Model
    model_path: str = "/home/gbarbadillo/data/Qwen2-0.5B-arc"
    max_model_len: int = 8192 #61000 for phi-3
    # Dataset
    #dataset_path: str = '/mnt/hdd0/Kaggle/arc24/data/arc-agi_evaluation_challenges.json'
    dataset_path: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    n_tasks: Optional[int] = None # Optional parameter to limit the number of task in the inference, set it to None to use all the tasks
    # Inference params
    predictions_per_task: int = 8 # How many predictions to make for each task, ideally should be a multiple of 8 (the number of geometric data augmentations)
    best_of: int = 1 # controls the number of beams used in beam search
    temperature: float = 0.0 # temperature for sampling, 0.0 for greedy search
    n: int = 1 # number of samples to generate


def parse_args():
    parser = argparse.ArgumentParser(description="Experiment Configuration")
    parser.add_argument('--model_path', type=str, help="Path to the model")
    parser.add_argument('--dataset_path', type=str, help="Path to the dataset to make inference")
    parser.add_argument('--n_tasks', type=int, help="If given only the first n tasks will be evaluated")
    parser.add_argument('--output_filepath', type=str, help="Path to the json file with the predictions")
    parser.add_argument('--predictions_per_task', type=int, help="Number of predictions per task, use a multiple of 8")
    parser.add_argument('--best_of', type=int, help="controls the number of beams used in beam search")
    parser.add_argument('--temperature', type=float, help="temperature for sampling, 0.0 for greedy search")
    parser.add_argument('--n', type=int, help="number of samples to generate")
    return parser.parse_args()


import json
import os
from tqdm.auto import tqdm
from itertools import islice, product

from vllm import LLM, SamplingParams
from transformers import AutoTokenizer

from arc24.data_augmentation import apply_data_augmentation, revert_data_augmentation, get_random_color_map
from arc24.prompting import SimplePromptCreator, print_smaller_prompt
from arc24.encoders import GridCodeBlockEncoder, MinimalGridEncoder

import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.info('Started logging')


def main():
    # Override default configuration using arguments
    args = parse_args()
    cfg = CFG(**{k: v for k, v in vars(args).items() if v is not None})
    print(asdict(cfg))

    with open(cfg.dataset_path) as f:
        data = json.load(f)
    if cfg.n_tasks is not None and cfg.n_tasks > 0:
        data = dict(islice(data.items(), cfg.n_tasks))
    print(f'There are {len(data)} tasks to solve.')


    print(f'Loading {cfg.model_path}')
    llm = LLM(model=cfg.model_path,
                trust_remote_code=True,
                dtype='half',
                tensor_parallel_size=2, # to use 2 gpus
                max_model_len=cfg.max_model_len,
                #kv_cache_dtype='fp8_e5m2', I have disabled kv cache quantization because it is hurtful
                enforce_eager=True, # without this 13.9GB of memory is used on each GPU, with this is 13.3GB,
                disable_log_stats=True,
                )
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_path)
    for number in '0123456789':
        print(f'{number}: {[key for key in tokenizer.get_vocab().keys() if number in key and not key.startswith("<")]}')


    prompt_creator = SimplePromptCreator(GridCodeBlockEncoder(MinimalGridEncoder()), tokenizer, cfg.model_path)
    prompts_conf = create_prompts(data, prompt_creator, cfg.predictions_per_task)
    prompts = [conf['prompt'] for conf in prompts_conf]
    print_smaller_prompt(prompts)

    sampling_params = get_sampling_params(cfg.best_of, cfg.temperature, cfg.n)
    # TODO: maybe I should create smaller batches, f.e. there were 54272 prompts when using 512 data augmentation
    outputs = llm.generate(prompts, sampling_params, use_tqdm=True)
    solutions = create_solutions(outputs, prompts_conf, prompt_creator, data)

    with open(cfg.output_filepath, 'w') as f:
        json.dump(solutions, f)
    # with open(cfg.output_filepath.replace('.json', '_rich.json'), 'w') as f:
    #     rich_output = create_rich_output(outputs, prompts_conf, prompt_creator)
    #     json.dump(rich_output, f)

    del llm.llm_engine.model_executor
    del llm
    clear_vllm_gpu_memory()


def create_prompts(data, prompt_creator, predictions_per_task):
    prompts = []
    for task_id, task in tqdm(data.items(), total=len(data), desc='Creating prompts'):
        data_augmentation_params = list(product([False, True], [0, 1, 2, 3]))
        for hflip, n_rot90 in data_augmentation_params:
            for _ in range(predictions_per_task//len(data_augmentation_params)):
                color_map = get_random_color_map(change_background_probability=0.1)
                data_augmentation_kwargs = dict(hflip=hflip, n_rot90=n_rot90, color_map=color_map)
                augmented_task = apply_data_augmentation(task, **data_augmentation_kwargs)
                task_prompts = prompt_creator.create_task_prompts(augmented_task)
                for idx, prompt in enumerate(task_prompts):
                    prompts.append(dict(task_id=task_id,
                                        data_augmentation_kwargs=data_augmentation_kwargs,
                                        prompt=prompt,
                                        idx=idx))
    return prompts


def get_sampling_params(best_of, temperature, n):
    # # https://docs.vllm.ai/en/latest/dev/sampling_params.html
    if best_of == 1:
        print('Using greedy search')
        sampling_params = SamplingParams(n=n, temperature=temperature, max_tokens=1000)
    else:
        print(f'Using beam search with best_of={best_of}, temperature is set to 0.0')
        sampling_params = SamplingParams(n=n, temperature=0.0, max_tokens=1000,
                              use_beam_search=True, best_of=best_of)
    print(f'Sampling params: {sampling_params}')
    return sampling_params


def create_solutions(outputs, prompts, prompt_creator, data):
    solutions = _create_empty_solutions(data)
    for idx, output in tqdm(enumerate(outputs), total=len(outputs), desc='Parsing outputs'):
        task_id = prompts[idx]['task_id']
        data_augmentation_kwargs = prompts[idx]['data_augmentation_kwargs']
        sample_idx = prompts[idx]['idx']
        response = output.outputs[0].text
        try:
            grid = prompt_creator.parse_response(response)
            grid = revert_data_augmentation(grid, **data_augmentation_kwargs)
        except Exception as e:
            # TODO: better exception printing (shape of the grid)
            print(f'Exception when parsing response from {task_id}_{sample_idx}: {e} {response}')
            grid = []
        attempt_name = f"attempt_{len(solutions[task_id][sample_idx]) + 1}"
        solutions[task_id][sample_idx][attempt_name] = grid
    return solutions


def create_rich_output(outputs, prompts_conf, prompt_creator):
    rich_output = prompts_conf
    for idx, output in tqdm(enumerate(outputs), total=len(outputs), desc='Creating rich output'):
        rich_output[idx]['cumulative_logprob'] = output.outputs[0].cumulative_logprob
        rich_output[idx]['n_tokens'] = len(output.outputs[0].token_ids)
        rich_output[idx]['response'] = output.outputs[0].text
        try:
            grid = prompt_creator.parse_response(output.outputs[0].text)
        except Exception as e:
            grid = []
        rich_output[idx]['grid'] = grid
    return rich_output



def _create_empty_solutions(data):
    solutions = dict()
    for task_id, task in data.items():
        solutions[task_id] = [dict() for _ in task['test']]
    return solutions


def clear_vllm_gpu_memory():
    # https://github.com/vllm-project/vllm/issues/1908
    from vllm.distributed.parallel_state import destroy_model_parallel, destroy_distributed_environment
    import torch
    import gc
    destroy_model_parallel()
    destroy_distributed_environment()
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == '__main__':
    main()