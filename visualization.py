import matplotlib.pyplot as plt
import matplotlib.style as style

from data.cifar10_dataset import Cifar10Dataset
from data.jurkat_dataset import JurkatDataset
from data.matek_dataset import MatekDataset
from data.plasmodium_dataset import PlasmodiumDataset
from data.config.matek_config import set_matek_configs
from data.config.jurkat_config import set_jurkat_configs
from data.config.plasmodium_config import set_plasmodium_configs
from results import ratio_metrics, ratio_class_wise_metrics, epoch_class_wise_loss, ae_loss
from options.visualization_options import get_arguments

import numpy as np

datasets = {'matek': MatekDataset, 'cifar10': Cifar10Dataset, 'plasmodium': PlasmodiumDataset, 'jurkat': JurkatDataset}
configs = {'matek': set_matek_configs, 'jurkat': set_jurkat_configs, 'plasmodium': set_plasmodium_configs}

plot_configs = {'matek': (2, 5),
                'jurkat': (2, 4),
                'plasmodium': (1, 2)}

"""
plot the accuracy vs data proportion being used, graph
credits to: Alex Olteanu (https://www.dataquest.io/blog/making-538-plots/) for the plot style
:return: None
"""


methods = [
    'random_sampling',
    'entropy_based',
    'learning_loss',
    'mc_dropout',
    'augmentations_based',
    'pseudo_labeling',
    'auto_encoder',
    'fixmatch',
    'simclr',
]


def plot_ratio_class_wise_metrics(metric, classes, label_y, prop, plot_config):
    fig = plt.figure(figsize=(20, 7))
    style.use('fivethirtyeight')

    colors = [[0, 0, 0, 1], [230 / 255, 159 / 255, 0, 1], [86 / 255, 180 / 255, 233 / 255, 1],
              [0, 158 / 255, 115 / 255, 1], [213 / 255, 94 / 255, 0, 1], [0, 114 / 255, 178 / 255, 1],
              [93 / 255, 58 / 255, 155 / 255, 1], [153 / 255, 79 / 255, 0, 1], [211 / 255, 95 / 255, 183 / 255, 1],
              [238 / 255, 136 / 255, 102 / 255, 1]]
    ax_main = fig.add_subplot(111)
    for i, cls in enumerate(classes):
        ax = fig.add_subplot(plot_config[0], plot_config[1], i+1)
        for j, method in enumerate(methods):
            if len(metric[j]) == 0:
                continue
            linestyle = '-'
            ax.errorbar(prop, metric[j][i][1], yerr=(metric[j][i][0]-metric[j][i][2])/2, color=colors[j % len(colors)],
                        label=methods[j], linewidth=2, linestyle=linestyle, marker='o', capsize=3)
            # ax.fill_between(prop, metric[j][i][0], metric[j][i][2], color=colors[i % len(colors)], alpha=0.05)
            ax.set_title(classes[i])

    ax_main.spines['top'].set_color('none')
    ax_main.spines['bottom'].set_color('none')
    ax_main.spines['left'].set_color('none')
    ax_main.spines['right'].set_color('none')
    ax_main.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False)

    ax_main.set_xlabel("Labeled ratio of the dataset", fontsize=20, weight='bold', alpha=.75)
    ax_main.set_ylabel(label_y, fontsize=20, weight='bold', alpha=.75)
    plt.show()


def plot_ratio_metrics(prop, metric, label_y):
    plt.figure(figsize=(14, 10))
    style.use('fivethirtyeight')

    colors = [[0, 0, 0, 1], [230 / 255, 159 / 255, 0, 1], [86 / 255, 180 / 255, 233 / 255, 1],
              [0, 158 / 255, 115 / 255, 1], [213 / 255, 94 / 255, 0, 1], [0, 114 / 255, 178 / 255, 1],
              [93 / 255, 58 / 255, 155 / 255, 1], [153 / 255, 79 / 255, 0, 1], [211 / 255, 95 / 255, 183 / 255, 1],
              [238 / 255, 136 / 255, 102 / 255, 1]]

    for i, method in enumerate(methods):
        if len(metric[i]) == 0:
            continue
        linestyle = '-'
        plt.errorbar(prop, metric[i][1], yerr=(metric[i][0]-metric[i][2])/2, color=colors[i % len(colors)],
                     label=method, linewidth=2, linestyle=linestyle, marker='o', capsize=3)
        plt.fill_between(prop, metric[i][0], metric[i][2], color=colors[i % len(colors)], alpha=0.05)

    plt.xlabel("Labeled ratio of the dataset", fontsize=20, weight='bold', alpha=.75)
    plt.ylabel(label_y, fontsize=20, weight='bold', alpha=.75)

    plt.legend(loc='lower right', fontsize=18)
    plt.show()


def plot_epoch_class_wise_loss(values, classes, label_y, epochs, plot_config):
    fig = plt.figure(figsize=(20, 7))
    style.use('fivethirtyeight')

    colors = [[0, 0, 0, 1], [230 / 255, 159 / 255, 0, 1], [86 / 255, 180 / 255, 233 / 255, 1],
              [0, 158 / 255, 115 / 255, 1], [213 / 255, 94 / 255, 0, 1], [0, 114 / 255, 178 / 255, 1],
              [93 / 255, 58 / 255, 155 / 255, 1], [153 / 255, 79 / 255, 0, 1], [211 / 255, 95 / 255, 183 / 255, 1],
              [238 / 255, 136 / 255, 102 / 255, 1]]
    ax_main = fig.add_subplot(111)
    for i, cls in enumerate(classes):
        ax = fig.add_subplot(plot_config[0], plot_config[1], i+1)
        if len(values[i]) == 0:
            continue
        linestyle = '-'
        ax.plot(epochs, values[i][0], color=colors[0], label='Train Loss',
                linewidth=2, linestyle=linestyle)
        ax.plot(epochs, values[i][1], color=colors[1], label='Valid Loss',
                linewidth=2, linestyle=linestyle)
        ax.set_title(classes[i])

    ax_main.spines['top'].set_color('none')
    ax_main.spines['bottom'].set_color('none')
    ax_main.spines['left'].set_color('none')
    ax_main.spines['right'].set_color('none')
    ax_main.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False)

    ax_main.set_xlabel("Epochs", fontsize=20, weight='bold', alpha=.75)
    ax_main.set_ylabel(label_y, fontsize=15, weight='bold', alpha=.75)
    plt.show()


def plot_ae_loss(losses, logs, epochs):
    plt.figure(figsize=(15, 10))
    style.use('fivethirtyeight')

    colors = [[0, 0, 0, 1], [230 / 255, 159 / 255, 0, 1], [86 / 255, 180 / 255, 233 / 255, 1],
              [0, 158 / 255, 115 / 255, 1], [213 / 255, 94 / 255, 0, 1], [0, 114 / 255, 178 / 255, 1],
              [93 / 255, 58 / 255, 155 / 255, 1], [153 / 255, 79 / 255, 0, 1], [211 / 255, 95 / 255, 183 / 255, 1],
              [238 / 255, 136 / 255, 102 / 255, 1]]

    for i, log in enumerate(logs):
        if i >= len(losses):
            break
        plt.plot(epochs, log, color=colors[i], label=losses[i], linewidth=2)

    plt.xlabel("Epochs", fontsize=20, weight='bold', alpha=.75)
    plt.ylabel("Loss Value", fontsize=20, weight='bold', alpha=.75)
    plt.legend(loc='lower right', fontsize=18)
    plt.show()


if __name__ == "__main__":
    args = get_arguments()
    args = configs[args.dataset](args)

    ratio = [i for i in np.arange(args.labeled_ratio_start, args.labeled_ratio_stop + args.add_labeled_ratio - 0.01,
                                  args.add_labeled_ratio)]

    dataset_class = datasets[args.dataset](root=args.root, oversampling=args.oversampling, merged=args.merged,
                                           remove_classes=args.remove_classes)

    dataset, _, _, _, _, _ = dataset_class.get_dataset()

    dataset_title = {'cifar10': ' cifar-10 dataset', 'matek': ' matek dataset', 'jurkat': ' jurkat dataset',
                     'plasmodium': ' plasmodium dataset'}
    y_label = f'{args.metric} on {dataset_title[args.dataset]}'
    y_label_alt = f'Losses for {methods[args.method_id]} on {dataset_title[args.dataset]}'

    ratio_class_wise_metrics_log = ratio_class_wise_metrics(args.metric, dataset.classes, args.dataset)
    plot_ratio_class_wise_metrics(ratio_class_wise_metrics_log, dataset.classes, y_label, ratio,
                                  plot_configs[args.dataset])

    ratio_metrics_logs = ratio_metrics(args.metric, args.dataset, cls=args.metric_ratio)
    plot_ratio_metrics(ratio, ratio_metrics_logs, y_label)

    epoch_class_wise_log = epoch_class_wise_loss(dataset.classes, methods[args.method_id], args.dataset)
    plot_epoch_class_wise_loss(epoch_class_wise_log, dataset.classes, y_label_alt,
                               list(range(len(epoch_class_wise_log[0][0]))), plot_configs[args.dataset])

    ae_loss_logs = ae_loss(args.dataset)
    plot_ae_loss(losses=['bce', 'l1', 'l2', 'ssim'], logs=ae_loss_logs, epochs=list(range(len(ae_loss_logs[0]))))
