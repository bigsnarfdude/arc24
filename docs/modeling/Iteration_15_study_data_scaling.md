# Iteration 15. Study how well this method scales with data

_01-09-2024_

## Goal

How the model accuracy scales with the number of training tasks?

## Motivation

Before taking a decision about the next steps, I want to know how well the current method scales with
the available training data.

## Development

The idea is to compare trainings that use the same number of steps (same compute) but use different
training data. I'm going to add an option to the fine-tuning script to subsample the train data.

I already have baseline results without subsampling. I'm going to try the following values: `[0.8, 0.6, 0.4, 0.2, 0.1]`

## Results

![data-scaling](res/2024-09-02-16-02-17.png)

Accuracy seems to improve linearly when scaling the data. F.e. having 1400 tasks for training should
yield an accuracy of 5%.

| training tasks | accuracy |
|----------------|----------|
| 700            | 2.80%    |
| 1400           | 5.60%    |
| 2800           | 11.20%   |
| 5000           | 20.00%   |
| 10000          | 40.00%   |
| 21250          | 85.00%   |

In the unlikely even that the trend continues "forever", it would be enough to generate 21k tasks to achieve the 500k reward.

## Conclusion

If we had access to more data with the same quality as the ARC tasks, it is very likely that we could improve the accuracy of our model.

## Next steps

- Revisit the study about external data
- Generate new data for training
