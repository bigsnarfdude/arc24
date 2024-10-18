# Iteration 42. Improve Omni-ARC

_14-10-2024_

## Goal

The idea is to devote at least a week to improve Omni-ARC dataset. At the same time I will run
daily trainings with the updated versions of the dataset and measure progress on the evaluation dataset.

## Motivation

The initial version of Omni-ARC has around 150 training tasks. A model trained on that version is
able to solve just 5% of the evaluation dataset. There should be a lot of room for improvement:

- Add more tasks to increase coverage
- Add more training inputs to have more variability (can I reuse re-arc for this?)
- Add task variations
- Add task to learn to use the primitives
- Implement the evaluation tasks (although this will only help to improve on leaderboard and will leak information of the evaluation set to my head)

## Development

### Implement more training tasks

I have increased the number of training tasks from 150 to 269.

### Make execution safer

I have found that one of the evaluations created a `colors.txt` file. I do not want the execution to
have input/output capabilities.

TODO: Once I have a model that is compatible with 0.3.0 version update the execution code to be safer: https://chatgpt.com/c/671217ca-e944-8012-a3b5-8b3a004a013a

### Creating more training inputs

Let's analyze how can I add more inputs for each task:

- Use re-arc dataset. This would be a great option if the re-arc dataset follows the same distribution
  as the original tasks (I'm not sure about this), because otherwise the task implementations won't work.
- Write my own python generators. It's very likely that with the right level of abstraction I can
  quickly implement generator for the training tasks. Requires more work than simply using re-arc.
- Use the model to generate new inputs. I have already trained models to learn the input distribution,
  thus it is possible to use those models to generate new inputs. The disadvantage of this approach
  is that I would have to manually verify the inputs. It is very likely that the model would fail
  to generate some inputs, so in those cases I would have to write python code. I might also need
  some grid editor to correct small mistakes in the inputs.

## Results

### First results

| omni-arc training tasks | training coverage | training pass_8 | evaluation pass_8 |
|-------------------------|-------------------|-----------------|-------------------|
| 150                     | 37.50%            | 35.80%          | 4.50%             |
| 269                     | 67.25%            | 62.60%          | 3.75%             |

First validation results do not show improvements on evaluation after increasing the number of tasks from 100 to 269.
The model is able to solve more training tasks, but its accuracy does not improve on the evaluation set.
These seems like a clear sign of overfitting.

I have visualized the tasks that it does correctly and they are all very similar to the training tasks. Thus
another evidence for overfitting.

Another explanation is that coverage on the evaluation dataset has not increased despite close to doubling
the coverage on the training dataset. But that seems to be very unlikely. I could measure coverage
on the evaluation set by implementing the evaluation tasks.

How could we reduce overfitting and improve generalization?

- Add more input samples. Currently we are just using the original task inputs with some data augmentation.
- Add more tasks. I could create task variations from the original tasks, or create entirely new
  tasks using the omni-arc domain specific language

This two actions should force the model to better learn the relation between examples and code.

It's very likely that the bad scaling behavior that we observed in recent iterations was caused by the
poor generalization. Thus if we unlock generalization it is possible that we are going to improve
the accuracy of the model, but also the model could improve given more compute (more predictions).

## Conclusion

## Next steps

- Many times I do an initial implementation and there is some little detail wrong. I correct the implementation
  and then it's fine. The ideal system should also have this opportunity. However training such a model
  will require a larger context length, and I cannot afford it with the current hardware.
- I have found one task that required looking at the test input to properly implement the function.
  Create a new version of the prompt that uses also the test input.

## TODO

- [ ] Restrict globals
- [ ] Analyze RE-ARC input distribution
- [ ] Analyze generated input distribution