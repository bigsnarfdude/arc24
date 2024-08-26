
import os
import random
import json
import numpy as np
from tqdm.auto import tqdm
import wandb
from typing import Optional
import argparse
from dataclasses import dataclass, asdict

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, PeftModel, prepare_model_for_kbit_training, get_peft_model
from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
from datasets import Dataset, IterableDataset

from arc24.encoders import create_grid_encoder
from arc24.data_augmentation import random_augment_task
from arc24.prompting import create_prompts_from_task, print_smaller_prompt
from arc24.data import load_arc_data_with_solutions


# from zero
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = None
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/combos/combo_v2.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240814_new_partition/12_combo-v2_Qwen2-0.5B-Instruct_lr1e-4_r32_12e3steps_b'
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  12000
    eval_steps: int = 50
    report_to: str = 'wandb'
    warmup_ratio = 0.05
    batch_size = 16
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 2
    learning_rate: float = 1e-4
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r = 32
    # data augmentation
    use_data_augmentation: bool = True
    max_train_permutations = 2 # tipically 2
    color_swaps: int = 4
    preserve_original_colors = False
    geometric_transforms = 8 # 0-8
    swap_train_and_test = True
    repeat_prompts = 0 # if bigger than 0 it will repeat the prompts that many times, useful to induce variation in the order of the prompts

# load optimizer state
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = '/mnt/hdd0/Kaggle/arc24/models/20240814_new_partition/01_new-train_Qwen2-0.5B-Instruct_lr1e-4_r32_8e3steps/checkpoint-6000'
    load_optimizer_state: bool = True
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7_n-1.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240818_load_optimizer_state/03_optimizer-at-init_Qwen2-0.5B-Instruct_lr1e-5_100steps_a'
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  100
    eval_steps: int = 50
    report_to: str = 'wandb'
    warmup_ratio = 0.1
    batch_size = 16
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 2
    learning_rate: float = 1e-5
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r = 32
    # data augmentation
    use_data_augmentation: bool = True
    max_train_permutations = 2 # tipically 2
    color_swaps: int = 1
    preserve_original_colors = False
    geometric_transforms = 8 # 0-8
    swap_train_and_test = True
    repeat_prompts = 0 # if bigger than 0 it will repeat the prompts that many times, useful to induce variation in the order of the prompts


# iterable dataset
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = '/mnt/hdd0/Kaggle/arc24/models/20240814_new_partition/01_new-train_Qwen2-0.5B-Instruct_lr1e-4_r32_8e3steps/checkpoint-6000'
    load_optimizer_state: bool = False
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7_n-1.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240818_iterable_dataset_v2/04_dataset-with-augmentation'
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  100
    eval_steps: int = 50
    report_to: str = 'wandb'
    warmup_ratio = 0.1
    batch_size = 16
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 2
    learning_rate: float = 1e-5
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r = 32
    # data augmentation
    use_data_augmentation: bool = True
    max_train_permutations = 2 # tipically 2
    color_swaps: int = 1
    preserve_original_colors = False
    geometric_transforms = 8 # 0-8
    swap_train_and_test = True
    repeat_prompts = 0 # if bigger than 0 it will repeat the prompts that many times, useful to induce variation in the order of the prompts

# train from RE-ARC
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = '/mnt/hdd0/Kaggle/arc24/models/20240814_new_partition/06_RE-ARC_Qwen2-0.5B-Instruct_lr1e-4_r32_8e3steps/checkpoint-1300'
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/train_rs7.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240814_new_partition/17_new-train-from-RE-ARC_Qwen2-0.5B-Instruct_lr1e-4_r32_6e3steps'
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  6000
    eval_steps: int = 50 #50
    report_to: str = 'wandb'
    warmup_ratio = 0.05
    batch_size = 16 #16
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 2
    learning_rate: float = 1e-4
    max_grad_norm: float = 1.0
    optim: str = "paged_adamw_8bit" # "paged_adamw_8bit"
    torch_dtype: str = "bfloat16" # "bfloat16" or "float16", float16 causes divergence when training on my PC, but it is 4x faster on Kaggle
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r = 32
    # data augmentation
    use_data_augmentation: bool = True
    max_train_permutations = 2 # tipically 2
    color_swaps: int = 4
    preserve_original_colors = False
    geometric_transforms = 8 # 0-8
    swap_train_and_test = True
    repeat_prompts = 0 # if bigger than 0 it will repeat the prompts that many times, useful to induce variation in the order of the prompts


# fast test time fine-tuning conf
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = '/mnt/hdd0/Kaggle/arc24/models/20240814_new_partition/01_new-train_Qwen2-0.5B-Instruct_lr1e-4_r32_8e3steps/checkpoint-6000'
    # train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/combos/combo_v2.json'
    # train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7_n-1.json'
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/combos/combo_v3.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240820_new_partition_ttft/04_combo-v3-constant-lr_Qwen2-0.5B-Instruct_lr1e-5_2e3steps'
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  2000 # 1000
    logging_steps: int = 10 #10
    eval_steps: int = 50 #50
    report_to: str = 'wandb'
    warmup_ratio = 0.1
    batch_size = 16 #16
    random_seed: Optional[int] = None
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 1 # if using 2 the validation loss is not correctly computed
    learning_rate: float = 1e-5
    lr_scheduler_type: str = "constant_with_warmup" #linear, constant_with_warmup, cosine, cosine_with_restarts
    max_grad_norm: float = 1.0
    optim: str = "paged_adamw_8bit" # "paged_adamw_8bit"
    torch_dtype: str = "bfloat16" # "bfloat16" or "float16", float16 causes divergence when training on my PC, but it is 4x faster on Kaggle
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r = 32


# fast test time fine-tuning conf 1.5B
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-1.5B-Instruct'
    adapter_path: Optional[str] = '/mnt/hdd0/Kaggle/arc24/models/20240820_new_partition/01_new-train_Qwen2-1.5B-Instruct_lr1e-4_r32_6e3steps/checkpoint-2500'
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7_n-1.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240820_new_partition_ttft/05_linear_Qwen2-1.5B-Instruct_lr1e-5_800steps'
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  800 # 1000
    logging_steps: int = 10 #10
    eval_steps: int = 50 #50
    report_to: str = 'wandb'
    warmup_ratio = 0.1
    batch_size = 16 #16
    random_seed: Optional[int] = None
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 1 # if using 2 the validation loss is not correctly computed
    learning_rate: float = 1e-5
    lr_scheduler_type: str = "linear" #linear, constant_with_warmup, cosine, cosine_with_restarts
    max_grad_norm: float = 1.0
    optim: str = "paged_adamw_8bit" # "paged_adamw_8bit"
    torch_dtype: str = "bfloat16" # "bfloat16" or "float16", float16 causes divergence when training on my PC, but it is 4x faster on Kaggle
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r = 32


# train from zero
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = None
    # train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/train_rs7.json'
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/combos/combo_v2.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240820_new_partition/02_combo-v2_Qwen2-0.5B-Instruct_lr1e-4_r32_6e3steps'
    n_gpus: int = 2
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  6000
    logging_steps: int = 10 #10a
    eval_steps: int = 100 #50
    report_to: str = 'wandb'
    warmup_ratio = 0.05
    batch_size = 16 #16
    random_seed: Optional[int] = None
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 1 # if using 2 the validation loss is not correctly computed
    learning_rate: float = 1e-4
    lr_scheduler_type: str = "linear" #linear, constant_with_warmup, cosine, cosine_with_restarts
    max_grad_norm: float = 1.0
    optim: str = "paged_adamw_8bit" # "paged_adamw_8bit"
    torch_dtype: str = "bfloat16" # "bfloat16" or "float16", float16 causes divergence when training on my PC, but it is 4x faster on Kaggle
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r: int = 32


# debug refactor
@dataclass
class CFG:
    model_path: str = 'Qwen/Qwen2-0.5B-Instruct'
    adapter_path: Optional[str] = None
    train_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/train_rs7.json'
    val_dataset: str = '/mnt/hdd0/Kaggle/arc24/data/new_partitions/val_rs7.json'
    output_dir: str = '/mnt/hdd0/Kaggle/arc24/models/20240826_debug_refactor/14_update_data_augmentation'
    n_gpus: int = 2
    max_seq_len: int = 4096
    epochs = 0
    max_steps : Optional[int] =  25
    logging_steps: int = 1 #10a
    eval_steps: int = 25 #50
    report_to: str = 'wandb'
    warmup_ratio = 0.05
    batch_size = 16 #16
    random_seed: Optional[int] = 7
    grid_encoder: str = 'GridCodeBlockEncoder(MinimalGridEncoder())'
    # SmolLM-135M-Instruct: (4, 4); Qwen/Qwen2-0.5B-Instruct: (1, 2)
    per_device_train_batch_size = 1
    per_device_eval_batch_size = 1 # if using 2 the validation loss is not correctly computed
    learning_rate: float = 1e-4
    lr_scheduler_type: str = "linear" #linear, constant_with_warmup, cosine, cosine_with_restarts
    max_grad_norm: float = 1.0
    optim: str = "paged_adamw_8bit" # "paged_adamw_8bit"
    torch_dtype: str = "bfloat16" # "bfloat16" or "float16", float16 causes divergence when training on my PC, but it is 4x faster on Kaggle
    # LoRA
    use_rslora = True,
    use_dora = True,
    lora_r: int = 32


def parse_args():
    parser = argparse.ArgumentParser(description="Experiment Configuration")
    parser.add_argument('--model_path', type=str, help="Path to the model")
    parser.add_argument('--adapter_path', type=str, help="Path to the LoRA adapter for initialization")
    parser.add_argument('--output_dir', type=str, help="Path to the output LoRA")
    parser.add_argument('--train_dataset', type=str, help="Path to the dataset for training")
    parser.add_argument('--val_dataset', type=str, help="Path to the dataset for validation")
    parser.add_argument('--max_steps', type=int, help="Max steps to fine-tune")
    parser.add_argument('--max_seq_len', type=int, help="Max sequence length in tokens")
    parser.add_argument('--eval_steps', type=int, help="Number of steps between evaluations")
    parser.add_argument('--learning_rate', type=float, help='Learning rate for fine-tuning')
    parser.add_argument('--report_to', type=str, help="Set it to tensorboard to disable wandb")
    parser.add_argument('--torch_dtype', type=str, help="Which dtype to use with torch")
    parser.add_argument('--lora_r', type=int, help="Rank of the LoRA adapter")
    parser.add_argument('--n_gpus', type=int, help="Number of gpus to use")
    parser.add_argument('--grid_encoder', type=str, help="Name of the grid encoder")
    return parser.parse_args()


def main():
    # Override default configuration using arguments
    cfg = CFG(**{k: v for k, v in vars(parse_args()).items() if v is not None})
    save_train_conf(cfg)

    model = get_model(cfg.model_path, cfg.n_gpus, cfg.torch_dtype)
    tokenizer = get_tokenizer(cfg.model_path, model)
    model = get_lora_model(model, cfg.adapter_path, cfg.lora_r, cfg.use_rslora, cfg.use_dora)

    grid_encoder = create_grid_encoder(cfg.grid_encoder)
    dataset_kwargs = {'grid_encoder': grid_encoder, 'tokenizer': tokenizer, 'max_seq_len': cfg.max_seq_len}
    train_dataset = IterableDataset.from_generator(
        prompt_generator,
        gen_kwargs=dict(filepath=cfg.train_dataset, random_seed=cfg.random_seed, **dataset_kwargs))
    val_dataset = create_validation_dataset(cfg.val_dataset, **dataset_kwargs)

    training_arguments = get_training_arguments(cfg)
    data_collator = get_data_collator(cfg.model_path, tokenizer)
    if cfg.report_to == 'wandb':
        w = wandb.init(reinit=True,
                dir=cfg.output_dir,
                project=os.path.basename(os.path.dirname(cfg.output_dir)),
                name=os.path.basename(cfg.output_dir))
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=cfg.max_seq_len,
        data_collator=data_collator,
        args=training_arguments,
        # optimizers=(torch.load(os.path.join(cfg.adapter_path, 'optimizer.pt')), None)
        # packing=True, # ValueError: You passed a `DataCollatorForCompletionOnlyLM` to the SFTTrainer. This is not compatible with the `packing` argument.
    )
    # if cfg.load_optimizer_state and cfg.adapter_path is not None:
    #     optimizer_path = os.path.join(cfg.adapter_path, 'optimizer.pt')
    #     if os.path.exists(optimizer_path):
    #         print(f'Loading optimizer from {optimizer_path}')
    #         trainer.create_optimizer()
    #         trainer.optimizer.load_state_dict(torch.load(optimizer_path))
    #     else:
    #         print(f'Optimizer not found on adapter path: {optimizer_path}')
    trainer.train()
    if cfg.report_to == 'wandb':
        w.finish()



# Model

def get_device_map(n_gpus, model_path):
    if n_gpus > 1:
        if 'llama' in model_path.lower():
            device_map = {
                'model.embed_tokens': 0,
                'model.layers.0': 0,
                'model.layers.1': 0,
                'model.layers.2': 0,
                'model.layers.3': 0,
                'model.layers.4': 0,
                'model.layers.5': 0,
                'model.layers.6': 0,
                'model.layers.7': 0,
                'model.layers.8': 0,
                'model.layers.9': 0,
                'model.layers.10': 0,
                'model.layers.11': 0,
                'model.layers.12': 0,
                'model.layers.13': 0,
                'model.layers.14': 0,
                'model.layers.15': 0,
                'model.layers.16': 0,
                'model.layers.17': 1,
                'model.layers.18': 1,
                'model.layers.19': 1,
                'model.layers.20': 1,
                'model.layers.21': 1,
                'model.layers.22': 1,
                'model.layers.23': 1,
                'model.layers.24': 1,
                'model.layers.25': 1,
                'model.layers.26': 1,
                'model.layers.27': 1,
                'model.layers.28': 1,
                'model.layers.29': 1,
                'model.layers.30': 1,
                'model.layers.31': 1,
                'model.norm': 1,
                'model.rotary_emb': 1,
                'lm_head': 1,
            }
        elif 'qwen2-0.5b-instruct' in model_path.lower():
            print('Using qwen2-0.5b-instruct device map')
            device_map = {
                'model.embed_tokens': 0,
                'lm_head': 0,
                'model.layers.0': 0,
                'model.layers.1': 0,
                'model.layers.2': 0,
                'model.layers.3': 0,
                'model.layers.4': 0,
                'model.layers.5': 0,
                'model.layers.6': 0,
                'model.layers.7': 0,
                'model.layers.8': 1,
                'model.layers.9': 1,
                'model.layers.10': 1,
                'model.layers.11': 1,
                'model.layers.12': 1,
                'model.layers.13': 1,
                'model.layers.14': 1,
                'model.layers.15': 1,
                'model.layers.16': 1,
                'model.layers.17': 1,
                'model.layers.18': 1,
                'model.layers.19': 1,
                'model.layers.20': 1,
                'model.layers.21': 1,
                'model.layers.22': 1,
                'model.layers.23': 1,
                'model.norm': 1
            }
        elif 'qwen2-1.5b-instruct' in model_path.lower():
            print('Using qwen2-1.5b-instruct device map')
            device_map = {
                'model.embed_tokens': 0,
                'lm_head': 0,
                'model.layers.0': 0,
                'model.layers.1': 0,
                'model.layers.2': 0,
                'model.layers.3': 0,
                'model.layers.4': 0,
                'model.layers.5': 0,
                'model.layers.6': 0,
                'model.layers.7': 0,
                'model.layers.8': 0,
                'model.layers.9': 0,
                'model.layers.10': 0,
                'model.layers.11': 1,
                'model.layers.12': 1,
                'model.layers.13': 1,
                'model.layers.14': 1,
                'model.layers.15': 1,
                'model.layers.16': 1,
                'model.layers.17': 1,
                'model.layers.18': 1,
                'model.layers.19': 1,
                'model.layers.20': 1,
                'model.layers.21': 1,
                'model.layers.22': 1,
                'model.layers.23': 1,
                'model.layers.24': 1,
                'model.layers.25': 1,
                'model.layers.26': 1,
                'model.layers.27': 1,
                'model.norm': 1}
        else:
            device_map = 'balanced'
    else:
        device_map = None
    return device_map


def get_flash_attention_implementation():
    try:
        import flash_attn
        attn_implementation = "flash_attention_2"
    except ImportError:
        attn_implementation = None
    print(f'Using {attn_implementation} attention implementation')
    return attn_implementation


def get_torch_dtype(torch_dtype):
    if torch_dtype == 'float16':
        print('Using float16 torch dtype')
        return torch.float16
    elif torch_dtype == 'bfloat16':
        print('Using bfloat16 torch dtype')
        return torch.bfloat16
    else:
        raise ValueError(f'Unknown torch dtype {torch_dtype}')


def get_model(model_path, n_gpus, torch_dtype):
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        #quantization_config=bnb_config,
        device_map=get_device_map(n_gpus, model_path),
        # max_memory={0: '9GB', 1: '8GB'},
        trust_remote_code=True,
        torch_dtype=get_torch_dtype(torch_dtype), #bfloat16 is 4 times slower on Kaggle than float16, on my computer they are the same speed
        attn_implementation=get_flash_attention_implementation(),
        )
    print_gpu_memory()
    return model


def get_tokenizer(model_path, model):
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True)
    if 'llama' in model_path:
        print('Adding <|pad|> token to tokenizer')
        tokenizer.add_special_tokens({'pad_token': '<|pad|>'})
        model.resize_token_embeddings(len(tokenizer))
        tokenizer.padding_side = 'right'
    print(tokenizer.special_tokens_map)
    print('Verification of number tokens')
    for number in '0123456789':
            print(f'{number}: {[key for key in tokenizer.get_vocab().keys() if number in key and not key.startswith("<")]}')
    return tokenizer


def get_lora_model(model, adapter_path, r, use_rslora, use_dora):
    if adapter_path is None:
        peft_config = LoraConfig(
            # lora_alpha: LoRA scaling factor.
            lora_alpha=64, #64,
            lora_dropout=0.1, # 0.1, althought Vaca suggested to use 0.05 for big models
            # r: the rank of the update matrices, expressed in int. Lower rank results in smaller update matrices with fewer trainable parameters.
            r=r, #16
            bias="none",
            task_type="CAUSAL_LM",
            # target_modules: The modules (for example, attention blocks) to apply the LoRA update matrices.
            target_modules= ['k_proj', 'q_proj', 'v_proj', 'o_proj'],
            use_rslora=use_rslora,
            use_dora=use_dora,
        )
        print(f'Creating LoRA with the following config: {peft_config}')
        model = get_peft_model(model, peft_config)
    else:
        print(f'Loading adapter from {adapter_path}')
        model = PeftModel.from_pretrained(model, adapter_path, is_trainable=True)
    return model


def print_gpu_memory():
    for device in range(torch.cuda.device_count()):
        print(f'GPU {device} memory allocated: {torch.cuda.memory_allocated(device)/1024**3:.1f} GB, max memory allocated: {torch.cuda.max_memory_allocated(device)/1024**3:.1f} GB')

# Data
def create_validation_dataset(filepath, grid_encoder, tokenizer, max_seq_len, print_sample_prompt=True):
    data = load_arc_data_with_solutions(filepath)
    tasks = list(data.values())
    prompts = []
    for task in tqdm(tasks, desc='create prompts'):
        prompts.extend(create_prompts_from_task(task, grid_encoder, tokenizer))
    if print_sample_prompt: print_smaller_prompt(prompts)
    prompt_lengths = [len(tokenizer.encode(prompt)) for prompt in tqdm(prompts, desc='Calculating prompt lengths')]
    print_prompt_length_percentiles(prompt_lengths)
    prompts = [prompt for prompt, prompt_length in zip(prompts, prompt_lengths) if prompt_length < max_seq_len]
    print(f'Leaving {len(prompts)} validation prompts after removing those longer than {max_seq_len} tokens')
    dataset = Dataset.from_dict({'text': prompts})
    return dataset


def prompt_generator(filepath, grid_encoder, tokenizer, max_seq_len, random_seed):
    data = load_arc_data_with_solutions(filepath)
    task_ids = list(data.keys())
    # TODO: log stats about too long prompts every so often
    random.seed(random_seed)
    np.random.seed(random_seed)
    while True:
        random.shuffle(task_ids)
        for task_id in task_ids:
            task = data[task_id]
            task = random_augment_task(task)
            prompts = create_prompts_from_task(task, grid_encoder, tokenizer)
            # TODO: is this the better way to deal with multi-output tasks?
            # Should I give more weight to tasks with multiple outputs?
            prompt = random.choice(prompts)
            prompt_length = len(tokenizer.encode(prompt))
            if prompt_length < max_seq_len:
                yield {'text': prompt}


def print_prompt_length_percentiles(prompt_lengths):
    for percentile in [50, 75, 90, 95, 97]:
        print(f'Prompt length percentile {percentile}: {np.percentile(prompt_lengths, percentile)}')

# Train
def get_data_collator(model_path, tokenizer):
    # TODO: create a function that returns model type from model path
    if 'llama' in model_path.lower():
        print('Using llama template for collator')
        data_collator = DataCollatorForCompletionOnlyLM(
            tokenizer=tokenizer,
            instruction_template='<|start_header_id|>user<|end_header_id|>',
            response_template='<|start_header_id|>assistant<|end_header_id|>',
        )
    elif 'SmolLM' in model_path.lower() or 'qwen' in model_path.lower():
        print('Using SmolLM template for collator')
        data_collator = DataCollatorForCompletionOnlyLM(
            tokenizer=tokenizer,
            instruction_template='<|im_start|>user',
            response_template='<|im_start|>assistant',
        )
    else:
        print('Using Phi-3 template for collator')
        data_collator = DataCollatorForCompletionOnlyLM(
            tokenizer=tokenizer,
            instruction_template='<|user|>',
            response_template='<|assistant|>'
        )
    return data_collator


def get_training_arguments(cfg):
    batch_size_kwargs = dict(
        # 4-16 batch size should be fine for lora.
        per_device_train_batch_size=cfg.per_device_train_batch_size,
        gradient_accumulation_steps=cfg.batch_size//cfg.per_device_train_batch_size,
        per_device_eval_batch_size=cfg.per_device_eval_batch_size,
    )

    training_arguments = TrainingArguments(
            output_dir=cfg.output_dir,
            num_train_epochs=cfg.epochs,
            max_steps=cfg.max_steps,
            warmup_ratio=cfg.warmup_ratio,
            learning_rate=cfg.learning_rate,
            lr_scheduler_type=cfg.lr_scheduler_type, #constant_with_warmup, cosine, cosine_with_restarts
            optim=cfg.optim,
            max_grad_norm=cfg.max_grad_norm,

            do_eval=True,
            evaluation_strategy="steps",
            save_steps=cfg.eval_steps,
            logging_steps=cfg.logging_steps, #50,
            eval_steps=cfg.eval_steps,
            log_level="info",
            report_to=cfg.report_to,

            **batch_size_kwargs
    )
    return training_arguments


def save_train_conf(cfg):
    print(asdict(cfg))
    os.makedirs(cfg.output_dir, exist_ok=True)
    with open(os.path.join(cfg.output_dir, 'cfg.json'), 'w') as f:
        json.dump({key:value for key, value in cfg.__dict__.items() if not key.startswith('__')}, f, indent=4)


if __name__ == '__main__':
    main()
