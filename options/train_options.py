import argparse

parser = argparse.ArgumentParser(description='Active Learning Basic Medical Imaging')

parser.add_argument('--epochs', default=1000, type=int,
                    help='number of total epochs to run')

parser.add_argument('--autoencoder-train-epochs', default=20, type=int,
                    help='number of total epochs to run')

parser.add_argument('--simclr-train-epochs', default=100, type=int,
                    help='number of total epochs to run')

parser.add_argument('--start-epoch', default=0, type=int,
                    help='manual epoch number (useful on restarts)')

parser.add_argument('-b', '--batch-size', default=128, type=int,
                    help='mini-batch size (default: 512)')

parser.add_argument('--lr', '--learning-rate', default=0.1, type=float,
                    help='initial learning rate')

parser.add_argument('--momentum', default=0.9, type=float, help='momentum')

parser.add_argument('--nesterov', default=True, type=bool, help='nesterov momentum')

parser.add_argument('--weight-decay', '--wd', default=5e-4, type=float,
                    help='weight decay (default: 5e-4)')

parser.add_argument('--print-freq', '-p', default=10, type=int,
                    help='print frequency (default: 10)')

parser.add_argument('--layers', default=28, type=int,
                    help='total number of layers (default: 28)')

parser.add_argument('--widen-factor', default=10, type=int,
                    help='widen factor (default: 10)')

parser.add_argument('--drop-rate', default=0.3, type=float,
                    help='dropout probability (default: 0.3)')

parser.add_argument('--no-augment', dest='augment', action='store_false',
                    help='whether to use standard augmentation (default: True)')

parser.add_argument('--resume', action='store_true', help='flag to be set if an existed model is to be loaded')

parser.add_argument('--name', default=' ', type=str,
                    help='name of experiment')

parser.add_argument('--add-labeled-epochs', default=20, type=int,
                    help='if the test accuracy stays stable for add-labeled-epochs epochs then add new data')

parser.add_argument('--add-labeled-ratio', default=0.025, type=int,
                    help='what percentage of labeled data to be added')

parser.add_argument('--labeled-ratio-start', default=0.05, type=int,
                    help='what percentage of labeled data to start the training with')

parser.add_argument('--labeled-ratio-stop', default=0.25, type=int,
                    help='what percentage of labeled data to stop the training process at')

parser.add_argument('--labeled-warmup_epochs', default=15, type=int,
                    help='how many epochs to warmup for, without sampling or pseudo labeling')

parser.add_argument('--arch', default='resnet', type=str, choices=['wideresnet', 'densenet', 'lenet', 'resnet'],
                    help='arch name')

parser.add_argument('--uncertainty-sampling-method', default='least_confidence', type=str,
                    choices=['least_confidence', 'margin_confidence', 'ratio_confidence', 'entropy_based',
                             'density_weighted', 'mc_dropout'],
                    help='the uncertainty sampling method to use')

parser.add_argument('--mc-dropout-iterations', default=25, type=int,
                    help='number of iterations for mc dropout')

parser.add_argument('--root', default='/home/qasima/datasets/thesis/stratified/', type=str,
                    help='the root path for the datasets')

parser.add_argument('--weak-supervision-strategy', default='semi_supervised', type=str,
                    choices=['active_learning', 'semi_supervised', 'random_sampling', 'fully_supervised'],
                    help='the weakly supervised strategy to use')

parser.add_argument('--semi-supervised-method', default='auto_encoder', type=str,
                    choices=['pseudo_labeling', 'auto_encoder', 'simclr'],
                    help='the semi supervised method to use')

parser.add_argument('--pseudo-labeling-threshold', default=0.3, type=int,
                    help='the threshold for considering the pseudo label as the actual label')

parser.add_argument('--simclr-temperature', default=0.1, type=float, help='the temperature term for simclr loss')

parser.add_argument('--simclr-normalize', action='store_false', help='normalize the hidden feat vectors in simclr')

parser.add_argument('--simclr-batch-size', default=1024, type=int,
                    help='mini-batch size for simclr (default: 1024)')

parser.add_argument('--simclr-arch', default='resnet', type=str, choices=['lenet', 'resnet'],
                    help='which encoder architecture to use for simclr')

parser.add_argument('--simclr-base-lr', default=0.25, type=float, help='base learning rate, rescaled by batch_size/256')
parser.add_argument('--simclr-optimizer', default='adam', type=str, choices=['adam', 'lars'],
                    help='which optimizer to use for simclr')

parser.add_argument('--weighted', action='store_true', help='to use weighted loss or not')

parser.add_argument('--eval', action='store_true', help='only perform evaluation and exit')

parser.add_argument('--dataset', default='matek', type=str, choices=['cifar10', 'matek', 'cifar100'],
                    help='the dataset to train on')

parser.add_argument('--checkpoint-path', default='/home/qasima/med_active_learning/runs/', type=str,
                    help='the directory root for saving/resuming checkpoints from')

parser.add_argument('--seed', default=9999, type=int, choices=[6666, 9999, 2323, 5555], help='the random seed to set')

parser.add_argument('--log-path', default='/home/qasima/med_active_learning/logs/', type=str,
                    help='the directory root for storing/retrieving the logs')

parser.add_argument('--store_logs', action='store_false', help='store the logs after training')

parser.add_argument('--run_batch', action='store_true', help='run all methods in batch mode')

parser.set_defaults(augment=True)

arguments = parser.parse_args()


def get_arguments():
    return arguments