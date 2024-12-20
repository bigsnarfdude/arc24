# Iteration 3. Fine-tune on ARC tasks

_29-07-2024_

<!---
The work is done using short iterations. Each iteration needs to have a very
clear goal. This allows to gain greater knowledge of the problem on each iteration.
--->

## Goal

Let's fine-tune an LLM on ARC tasks and see if:

1. Can I learn/overfit the train and eval tasks?
2. Does learning the train or eval tasks improves the accuracy of the model on the other dataset?
3. Does training on train/eval tasks improves the results on test dataset?
4. Does it help to start from a model that learned to count?

## Motivation

On the previous iteration I have fine-tuned a Phi-3 model to learn to count. However it seemed that
the capacity to solve ARC tasks was worsened due to that fine-tuning. I still believe that learning
core knowledge priors is important, but maybe we have to do a multi-step learning process: first learn
the priors and second learn to solve the training tasks.

## Development

### Iterable dataset

I have tried implementing an Iterable dataset for the train dataset, which would be more memory efficient
and training will start faster. However it seems that `SFTTrainer` is not ready for it.

### Train script

I'm going to copy and adapt the script that was used to teach the models to count. It's a little bit
dirty but that will allow to start training quickly. Later I could think about refactoring a single
training script.

I'm going to apply rotations and flips to augment the train samples by x8. I also believe I could
swap some of the train samples by the test sample to increase the dataset by an additionally x4 (estimated)
Thus in the best case I will take the 400 train samples and get 12800.

I have concerns about the memory usage. When training to learn to count the number of tokens was below 1k, but here it might grow to 8k.

TODO: color swap (does it have sense?) or to remap the colors on each task

### GPU memory requirements

With 2x24GB of gpu memory I can only fit one sample of 4096 tokens when fine-tuning Phi-3. I cannot fine-tune Llama 3, at least without quantization.

### Going to the cloud

#### AWS

P5 instances have 8xH100 GPUs and P4 instances have 8xA100 GPUs. There does not seem to be an option
with a smaller number of GPUs.

#### Google Cloud

Google cloud allows to create machines with [1 or more A100 GPUs](https://cloud.google.com/compute/docs/gpus#a100-gpus), f.e. `a2-highgpu-1g`, `a2-ultragpu-1g`, `a2-highgpu-2g`... Ultra machines have 80GB of GPU memory, the others have 40GB.

When it comes to [H100 GPUs](https://cloud.google.com/compute/docs/gpus#h100-gpus) we have to use 8, there are no smaller options.

I don't see any other available option in Google Cloud with 40GB or more.

#### [Vast.ai](https://vast.ai/)

The prices here are also much better than in Google Cloud.

#### [Lambdalabs](https://lambdalabs.com/service/gpu-cloud#pricing)

After a quick comparison the prices on Lambdalabs seem to be much better than Google Cloud. So I'm probably starting here.

#### Veridas cluster

### RE-ARC

I have published a [notebook](https://www.kaggle.com/code/ironbar/generate-training-samples-using-re-arc) to generate training data in the same format as ARC tasks.

## Results

[Training metrics on wandb](https://wandb.ai/guillermobarbadillo/20240729_arc_fine_tuning/workspace?nw=nwuserguillermobarbadillo)

### Can we overfit to the train set?

| experiment                          | accuracy |
|-------------------------------------|----------|
| Phi-3 baseline                      | 1.6%     |
| Phi-3 baseline dialog               | 6.4%     |
| Fine-tune without data augmentation | 94.3%    |

We can improve the accuracy of the train set if we fine-tune on the train set.
I had to disable KV cache quantization to achieve that accuracy, check section below.

### Can we improve eval accuracy if we fine-tune on the train set?

| experiment                       | accuracy |
|----------------------------------|----------|
| Phi-3 baseline                   | 0.0%     |
| Phi-3 baseline dialog            | 2.5%     |
| Fine-tune with data augmentation | 6.2%     |

The table shows a clear improvement after fine-tuning the model on the train data. Thus we can
see that there is some generalization.

By training on the train dataset the validation loss is decreased. Data augmentation is helpful to decrease the validation loss

Could I try with test time fine-tuning to improve the accuracy?

### Does it help to start from a model that learned to count?

Starting from the model that was taught to count is not helpful, starting loss is higher and also final.
This follows the bad results observed when trying to solve arc tasks with that model. Thus it seems
that doing a previous fine-tuning in count tasks is not helpful. Maybe a single stage fine-tuning
could be better.

![train metrics](res/2024-08-01-13-11-22.png)

### Dimensions of the data

Training with re-arc allows me to learn how the different dimensions help to generalize:

- number of tasks
- different examples per task

The plot below shows the train and validation loss for different experiments. The validation dataset
is fixed, but the train dataset is different and data augmentation is also changed.

![dimensions of the data](res/2024-08-02-07-50-04.png)

This plots suggest that the number of different tasks is more important than having different examples
per task. When using the re-arc dataset that has 100 different variations of the same task (`07_phi-3`)
we can see that the training has a similar dynamic to using the train dataset without data augmentation:
the model does not generalize to the eval dataset and the train loss decreases fast.
The effect of having x100 more data is seen in the fact that it is harder to decrease the train loss
and the divergence in the eval dataset is slower, but the dynamic is the same.

In the other hand if we apply data augmentation to the re-arc dataset we see that the eval loss improves (`08_phi-3`)
and decreasing the train loss is more difficult. When we apply data augmentations such as geometric transformations
or color swaps we can transform the task (sometimes the task won't be changed, it depends on symmetries).
This is a very strong evidence that the number of different tasks is much more important than the number of
variations of the same task. Thus if I could create a task generator it would be valuable, or if I get other arc-like datasets. This has sense because the model is evaluated on new tasks, so ideally it would be trained
in all different tasks.

Training on the arc dataset reaches a lower validation loss than on the re-arc dataset. My guess is that
the distribution of the samples is more similar to the evaluation. The re-arc dataset has different colors
and sizes distribution.

#### Do not preserve the original colors of the tasks

![](res/2024-08-02-12-54-51.png)

The plots above show the exactly same experiment with just one variation: the orange line uses color
swap data augmentation in addition to using the original task colors, the green line does not preserve
the original colors, applies augmentation to all the tasks.

The difference in validation loss is dramatic. This is another strong evidence in favour of having
as many different tasks as possible in training.

### Training with re-arc is slower

I don't know exactly why, but training with re-arc dataset is slower than training with arc dataset. My guess is that each batch is padded to the element with the max length. I'm using a batch size of just 1, so I guess the difference in speed is simply due to the re-arc dataset
having a mean prompt length higher than arc.

It is 70% slower (145 vs 247 min for the same number of steps).

The re-arc dataset has different distribution than the ARC dataset: different sizes and colors.

### KV cache quantization is harmful!

I have found the reason for not being able to overfit and get good accuracies on the train set: KV cache quantization

| model    | accuracy quantized | accuracy not quantized |
|----------|--------------------|------------------------|
| 02_phi-3 | 60.20%             | 94.30%                 |
| 11_phi-3 | 43.20%             | 78.60%                 |

The table above shows train accuracy for models that have been trained to overfit on the train dataset.
It can be shown a huge improvement when not quantizing the kv cache.

TODO: what about regular not overfitted models?

### Submission

| model                                                                            | train  | eval  | test |
|----------------------------------------------------------------------------------|--------|-------|------|
| 10_phi-3_1rearc100_2train_lr5e-5_color-swap-no-preserve_continue/checkpoint-1000 | 24.50% | 6.13% | 3%   |

We have improved the test score from 1 (with Llama 3) to 3 by submitting a fine-tuned version of Phi-3.
Train accuracy is low, so I believe we should be able to improve it by increasing the model capacity or the train duration.

## Conclusion

On this iteration I have probed with Phi-3 that:

- I can overfit to the train set
- Fine-tuning on train set improves accuracy on the eval dataset
- Starting from a model that learned to count was not helpful
- The most important feature of the train set is to have different tasks. We have to train on the biggest number possible of different tasks.
  Using data augmentations that change the meaning of the task, such as geometric transformations or color swaps are very helpful.
- The re-arc dataset has different distribution than the ARC dataset: different sizes and colors. Its utility is limited because of this difference

We have improved the leaderboard score from 1 to 3.

## Next steps

- Could I frame the problem as a 2 player game where the first player needs to describe in text the
  transformation and the second player needs to implement it given the text description and the input?
- I need more computing power
- I could study different active inference techniques on the eval dataset. F.e. n-1 train. Eval loss should be a good proxy to see if the different techniques are useful
- [smollm](https://huggingface.co/blog/smollm)
- The number of different tasks is the more important factor during training. Thus downloading ARC like datasets
  or creating a task synthesizer would be valuable. Maybe the MindsAI team knows this and is simply
  working to implement new tasks, train a model on them and use test time inference. This hypothesis
  seems very plausible to me: they would have the advantage of using more data and the new test inference
  technique.
- I would like to make submissions with the fine-tuned models
- Does predicting the grid shape helps? Previosly to predict the grid print the shape. Maybe also on the input and output pairs. I have the intuition that this will help. Previously to do this I should refactor the code
 to enable easy experimentation with different prompts.
- What if I add new symbols to the tokenizer to represent the grids: <0>, <1>...

## TODO

- [x] Evaluate fine-tuned model on arc tasks
- [x] Prepare hodel data
- [ ] Try again with the iterable dataset: https://huggingface.co/docs/trl/en/sft_trainer#trl.trainer.ConstantLengthDataset
- [x] What if I first fine-tune with augmentation and then without augmentation
- [ ] Maybe not preserving the original color space creates a more challenging train dataset that results on better generalization.
- [ ] Improve evaluation notebook
  - [x] Free gpu memory after run
  - [x] Wait for free gpu
  - [ ] Better configuration
  - [x] Verify that training and evaluation is the same. They are the exact same prompt.
  - [ ] Should I refactor the way to create train and validation samples?
- [ ] Is there a relation between train loss and accuracy?
- [x] Make a submission with a fine-tuned model, to do this I should create a new notebook.
  - [ ] How to handle code and data in Kaggle