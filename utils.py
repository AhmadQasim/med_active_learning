from datetime import datetime

import json
import numpy as np
import os
import shutil
import math
import random

import torch
import torch.nn as nn
import torchvision

from numpy.random import default_rng
from sklearn.metrics import precision_recall_fscore_support, classification_report, confusion_matrix, roc_auc_score
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader
from torchlars import LARS

from model.densenet import densenet121
from model.lenet import LeNet
from model.loss_net import LossNet
from model.resnet import resnet18
from model.resnet_autoencoder import ResnetAutoencoder
from model.simclr_arch import SimCLRArch
from model.wideresnet import WideResNet
from augmentations.randaugment import RandAugmentMC


def save_checkpoint(args, state, is_best, filename='checkpoint.pth.tar', best_model_filename='model_best.pth.tar'):
    directory = os.path.join(args.checkpoint_path, args.name)
    if not os.path.exists(directory):
        os.makedirs(directory)
    filename = os.path.join(directory, filename)
    torch.save(state, filename)
    if is_best:
        shutil.copyfile(filename, os.path.join(directory, best_model_filename))


class AverageMeter(object):
    def __init__(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


class View(nn.Module):
    def __init__(self, shape):
        super(View, self).__init__()
        self.shape = shape

    def forward(self, x):
        batch_size = x.shape[0]
        x = x.view(batch_size, *self.shape)
        return x


class Flatten(nn.Module):
    def __init__(self):
        super(Flatten, self).__init__()

    def forward(self, x):
        batch_size = x.shape[0]
        return x.view(batch_size, -1)


def accuracy(output, target, topk=(1,)):
    maxk = max(topk)
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))

    res = []
    for k in topk:
        correct_k = correct[:k].view(-1).float().sum(0)
        res.append(correct_k.mul_(100.0 / batch_size))
    return res


def create_loaders(args, labeled_dataset, unlabeled_dataset, test_dataset, labeled_indices, unlabeled_indices, kwargs,
                   unlabeled_subset_num):
    labeled_dataset.indices = labeled_indices
    random.shuffle(unlabeled_indices)
    unlabeled_dataset.indices = unlabeled_indices[:unlabeled_subset_num]

    labeled_loader = DataLoader(dataset=labeled_dataset, batch_size=args.batch_size, shuffle=True, **kwargs)
    unlabeled_loader = DataLoader(dataset=unlabeled_dataset, batch_size=args.batch_size, shuffle=False, **kwargs)
    val_loader = DataLoader(dataset=test_dataset, batch_size=args.batch_size, shuffle=True, **kwargs)

    return labeled_loader, unlabeled_loader, val_loader


def create_base_loader(base_dataset, kwargs, batch_size):
    return DataLoader(dataset=base_dataset, batch_size=batch_size, drop_last=True, shuffle=True, **kwargs)


def stratified_random_sampling(unlabeled_indices, number):
    rng = default_rng()
    samples_indices = rng.choice(unlabeled_indices.shape[0], size=number, replace=False)

    return samples_indices


def postprocess_indices(labeled_indices, unlabeled_indices, samples_indices):
    unlabeled_mask = torch.ones(size=(len(unlabeled_indices),), dtype=torch.bool)
    unlabeled_mask[samples_indices] = 0
    labeled_indices = np.hstack([labeled_indices, unlabeled_indices[~unlabeled_mask]])
    unlabeled_indices = unlabeled_indices[unlabeled_mask]

    return labeled_indices, unlabeled_indices


class Metrics:
    def __init__(self):
        self.targets = []
        self.outputs = []
        self.outputs_probs = None

    def add_mini_batch(self, mini_targets, mini_outputs):
        self.targets.extend(mini_targets.tolist())
        self.outputs.extend(torch.argmax(mini_outputs, dim=1).tolist())
        self.outputs_probs = mini_outputs \
            if self.outputs_probs is None else torch.cat([self.outputs_probs, mini_outputs], dim=0)

    def get_metrics(self):
        return precision_recall_fscore_support(self.targets, self.outputs, average='macro', zero_division=1)

    def get_report(self):
        return classification_report(self.targets, self.outputs, zero_division=1)

    def get_confusion_matrix(self):
        return confusion_matrix(self.targets, self.outputs)

    def get_roc_auc_curve(self):
        self.outputs_probs = torch.softmax(self.outputs_probs, dim=1)
        return roc_auc_score(self.targets, self.outputs_probs.cpu().numpy(), multi_class='ovr')


class NTXent(nn.Module):
    def __init__(self, batch_size, temperature, device):
        super(NTXent, self).__init__()
        self.temperature = temperature
        self.device = device
        self.criterion = nn.CrossEntropyLoss(reduction="sum")
        self.similarity_f = nn.CosineSimilarity(dim=2)
        self.batch_size = batch_size
        self.mask = self.mask_correlated_samples()

    def mask_correlated_samples(self):
        # noinspection PyTypeChecker
        mask = torch.ones((self.batch_size * 2, self.batch_size * 2), dtype=bool)
        mask = mask.fill_diagonal_(0)
        for i in range(self.batch_size):
            mask[i, self.batch_size + i] = 0
            mask[self.batch_size + i, i] = 0
        return mask

    def forward(self, z_i, z_j):
        p1 = torch.cat((z_i, z_j), dim=0)
        sim = self.similarity_f(p1.unsqueeze(1), p1.unsqueeze(0)) / self.temperature

        sim_i_j = torch.diag(sim, self.batch_size)
        sim_j_i = torch.diag(sim, -self.batch_size)

        positive_samples = torch.cat((sim_i_j, sim_j_i), dim=0).reshape(
            self.batch_size * 2, 1
        )

        negative_samples = sim[self.mask].reshape(self.batch_size * 2, -1)

        labels = torch.zeros(self.batch_size * 2).to(self.device).long()
        logits = torch.cat((positive_samples, negative_samples), dim=1)
        loss = self.criterion(logits, labels)
        loss /= 2 * self.batch_size

        return loss


class TransformsSimCLR:
    def __init__(self, size):
        s = 1
        color_jitter = torchvision.transforms.ColorJitter(
            0.8 * s, 0.8 * s, 0.8 * s, 0.2 * s
        )
        self.train_transform = torchvision.transforms.Compose(
            [
                torchvision.transforms.RandomResizedCrop(size=size),
                torchvision.transforms.RandomHorizontalFlip(),
                torchvision.transforms.RandomApply([color_jitter], p=0.8),
                torchvision.transforms.RandomGrayscale(p=0.2),
                torchvision.transforms.ToTensor(),
            ]
        )

        self.test_transform = torchvision.transforms.Compose(
            [
                torchvision.transforms.Resize(size=(size, size)),
                torchvision.transforms.ToTensor(),
            ]
        )

    def __call__(self, x):
        return self.train_transform(x), self.train_transform(x)


class TransformFix(object):
    def __init__(self, mean, std, input_size=32):
        self.weak = torchvision.transforms.Compose([
            torchvision.transforms.RandomHorizontalFlip(),
            torchvision.transforms.RandomCrop(size=input_size, padding=int(input_size*0.125), padding_mode='reflect'),
        ])
        self.strong = torchvision.transforms.Compose([
            torchvision.transforms.RandomHorizontalFlip(),
            torchvision.transforms.RandomCrop(size=input_size, padding=int(input_size*0.125), padding_mode='reflect'),
            RandAugmentMC(n=2, m=10)
        ])
        self.normalize = torchvision.transforms.Compose([
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Normalize(mean=mean, std=std)
        ])

    def __call__(self, x):
        weak = self.weak(x)
        strong = self.strong(x)
        return self.normalize(weak), self.normalize(strong)


def create_model_optimizer_scheduler(args, dataset_class, optimizer='adam', scheduler='steplr',
                                     load_optimizer_scheduler=False):
    if args.arch == 'wideresnet':
        model = WideResNet(depth=args.layers,
                           num_classes=dataset_class.num_classes,
                           widen_factor=args.widen_factor,
                           dropout_rate=args.drop_rate)
    elif args.arch == 'densenet':
        model = densenet121(num_classes=dataset_class.num_classes)
    elif args.arch == 'lenet':
        model = LeNet(num_channels=3, num_classes=dataset_class.num_classes,
                      droprate=args.drop_rate, input_size=dataset_class.input_size)
    elif args.arch == 'resnet':
        model = resnet18(num_classes=dataset_class.num_classes, input_size=dataset_class.input_size)
    else:
        raise NotImplementedError

    print('Number of model parameters: {}'.format(
        sum([p.data.nelement() for p in model.parameters()])))

    model = model.cuda()

    if optimizer == 'adam':
        optimizer = torch.optim.Adam(model.parameters())
    else:
        optimizer = torch.optim.SGD(model.parameters(), lr=args.lr,
                                    momentum=args.momentum, nesterov=args.nesterov)

    if scheduler == 'steplr':
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=50, gamma=0.2)
    else:
        args.iteration = args.fixmatch_k_img // args.batch_size
        args.total_steps = args.fixmatch_epochs * args.iteration
        scheduler = get_cosine_schedule_with_warmup(
            optimizer, args.fixmatch_warmup * args.iteration, args.total_steps)

    if args.resume:
        if load_optimizer_scheduler:
            model, optimizer, scheduler = resume_model(args, model, optimizer, scheduler)
        else:
            model, _, _ = resume_model(args, model)

    return model, optimizer, scheduler


def create_model_optimizer_simclr(args, dataset_class):
    model = SimCLRArch(num_channels=3,
                       num_classes=dataset_class.num_classes,
                       drop_rate=args.drop_rate, normalize=True, arch=args.simclr_arch,
                       input_size=dataset_class.input_size)

    model = model.cuda()

    args.resume = True
    if args.resume:
        model, _, _ = resume_model(args, model)
        args.start_epoch = args.epochs

    if args.simclr_optimizer == 'adam':
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
        scheduler = None
    else:
        args.simclr_base_lr = args.simclr_base_lr * (args.batch_size / 256)
        base_optimizer = torch.optim.SGD(model.parameters(), lr=args.lr,
                                         weight_decay=1e-6, momentum=args.momentum)
        optimizer = LARS(base_optimizer, trust_coef=1e-3)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, args.simclr_train_epochs,
                                                               eta_min=0, last_epoch=-1)

    return model, optimizer, scheduler, args


def create_model_optimizer_autoencoder(args, dataset_class):
    model = ResnetAutoencoder(z_dim=32, num_classes=dataset_class.num_classes, drop_rate=args.drop_rate,
                              input_size=dataset_class.input_size)

    model = model.cuda()

    args.resume = True
    if args.resume:
        file = os.path.join(args.checkpoint_path, args.name, 'model_best.pth.tar')
        if os.path.isfile(file):
            print("=> loading checkpoint '{}'".format(file))
            checkpoint = torch.load(file)
            args.start_epoch = checkpoint['epoch']
            args.start_epoch = args.epochs
            model.load_state_dict(checkpoint['state_dict'])
            print("=> loaded checkpoint '{}' (epoch {})"
                  .format(args.resume, checkpoint['epoch']))
        else:
            print("=> no checkpoint found at '{}'".format(file))

    optimizer = torch.optim.Adam(model.parameters())

    return model, optimizer, args


def create_model_optimizer_loss_net():
    model = LossNet().cuda()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    return model, optimizer


def get_loss(args, base_dataset, reduction='mean'):
    if args.weighted:
        classes_targets = np.array(base_dataset.targets)
        classes_samples = [np.sum(classes_targets == i) for i in range(len(base_dataset.classes))]
        # classes_weights = np.log2(len(base_dataset)) - np.log2(classes_samples)
        classes_weights = len(base_dataset) / np.array(classes_samples)
        # noinspection PyArgumentList
        criterion = nn.CrossEntropyLoss(weight=torch.FloatTensor(classes_weights).cuda(), reduction=reduction)
    else:
        criterion = nn.CrossEntropyLoss(reduction=reduction).cuda()

    return criterion


def loss_module_objective_func(pred, target, margin=1.0, reduction='mean'):
    assert len(pred) % 2 == 0, 'the batch size is not even.'
    assert pred.shape == pred.flip(0).shape

    pred = (pred - pred.flip(0))[:len(pred) // 2]
    target = (target - target.flip(0))[:len(target) // 2]
    target = target.detach()

    indicator_func = 2 * torch.sign(torch.clamp(target, min=0)) - 1

    if reduction == 'mean':
        loss = torch.sum(torch.clamp(margin - indicator_func * pred, min=0))
        loss = loss / pred.size(0)
    elif reduction == 'none':
        loss = torch.clamp(margin - indicator_func * pred, min=0)
    else:
        loss = None
        NotImplementedError()

    return loss


def resume_model(args, model, optimizer=None, scheduler=None):
    file = os.path.join(args.checkpoint_path, args.name, 'model_best.pth.tar')
    if os.path.isfile(file):
        print("=> loading checkpoint '{}'".format(file))
        checkpoint = torch.load(file)
        args.start_epoch = checkpoint['epoch']
        model.load_state_dict(checkpoint['state_dict'])
        if optimizer:
            optimizer.load_state_dict(checkpoint['optimizer'])
        if scheduler:
            scheduler.load_state_dict(checkpoint['scheduler'])
        print("=> loaded checkpoint '{}' (epoch {})"
              .format(args.resume, checkpoint['epoch']))
    else:
        print("=> no checkpoint found at '{}'".format(file))

    return model, optimizer, scheduler


def set_model_name(args):
    if args.weak_supervision_strategy == 'semi_supervised':
        name = f"{args.dataset}@{args.arch}@{args.semi_supervised_method}"
    elif args.weak_supervision_strategy == 'active_learning':
        name = f"{args.dataset}@{args.arch}@{args.uncertainty_sampling_method}"
    else:
        name = f"{args.dataset}@{args.arch}@{args.weak_supervision_strategy}"

    return name


def perform_sampling(args, uncertainty_sampler, pseudo_labeler, epoch, model, train_loader, unlabeled_loader,
                     dataset_class, labeled_indices, unlabeled_indices, labeled_dataset, unlabeled_dataset,
                     test_dataset, kwargs, current_labeled_ratio, best_model):
    if args.weak_supervision_strategy == 'active_learning':
        samples_indices = uncertainty_sampler.get_samples(epoch, args, model,
                                                          train_loader,
                                                          unlabeled_loader,
                                                          number=dataset_class.add_labeled_num)

        labeled_indices, unlabeled_indices = postprocess_indices(labeled_indices, unlabeled_indices,
                                                                 samples_indices)

        train_loader, unlabeled_loader, val_loader = create_loaders(args, labeled_dataset, unlabeled_dataset,
                                                                    test_dataset, labeled_indices,
                                                                    unlabeled_indices, kwargs,
                                                                    dataset_class.unlabeled_subset_num)

        print(f'Uncertainty Sampling\t '
              f'Current labeled ratio: {current_labeled_ratio + args.add_labeled_ratio}\t'
              f'Model Reset')
    elif args.weak_supervision_strategy == 'semi_supervised':
        samples_indices, samples_targets = pseudo_labeler.get_samples(epoch, args, best_model,
                                                                      unlabeled_loader,
                                                                      number=dataset_class.add_labeled_num)

        labeled_indices, unlabeled_indices = postprocess_indices(labeled_indices, unlabeled_indices,
                                                                 samples_indices)

        pseudo_labels_acc = np.zeros(samples_indices.shape[0])
        for i, j in enumerate(samples_indices):
            if labeled_dataset.targets[j] == samples_targets[i]:
                pseudo_labels_acc[i] = 1
            else:
                labeled_dataset.targets[j] = samples_targets[i]

        train_loader, unlabeled_loader, val_loader = create_loaders(args, labeled_dataset, unlabeled_dataset,
                                                                    test_dataset, labeled_indices,
                                                                    unlabeled_indices, kwargs,
                                                                    dataset_class.unlabeled_subset_num)

        print(f'Pseudo labeling\t '
              f'Current labeled ratio: {current_labeled_ratio + args.add_labeled_ratio}\t'
              f'Pseudo labeled accuracy: {np.sum(pseudo_labels_acc == 1) / samples_indices.shape[0]}\t'
              f'Model Reset')

    else:
        samples_indices = stratified_random_sampling(unlabeled_indices, number=dataset_class.add_labeled_num)

        labeled_indices, unlabeled_indices = postprocess_indices(labeled_indices, unlabeled_indices,
                                                                 samples_indices)

        train_loader, unlabeled_loader, val_loader = create_loaders(args, labeled_dataset, unlabeled_dataset,
                                                                    test_dataset, labeled_indices,
                                                                    unlabeled_indices, kwargs,
                                                                    dataset_class.unlabeled_subset_num)

        print(f'Random Sampling\t '
              f'Current labeled ratio: {current_labeled_ratio + args.add_labeled_ratio}\t'
              f'Model Reset')

    return train_loader, unlabeled_loader, val_loader, labeled_indices, unlabeled_indices


def get_cosine_schedule_with_warmup(optimizer,
                                    num_warmup_steps,
                                    num_training_steps,
                                    num_cycles=7. / 16.,
                                    last_epoch=-1):
    def _lr_lambda(current_step):
        if current_step < num_warmup_steps:
            return float(current_step) / float(max(1, num_warmup_steps))
        no_progress = float(current_step - num_warmup_steps) / float(max(1, num_training_steps - num_warmup_steps))
        return max(0., math.cos(math.pi * num_cycles * no_progress))

    # noinspection PyTypeChecker
    return LambdaLR(optimizer, _lr_lambda, last_epoch)


def print_args(args):
    print('Arguments:\n'
          f'Model name: {args.name}\t'
          f'Epochs: {args.epochs}\t'
          f'Batch Size: {args.batch_size}\n'
          f'Architecture: {args.arch}\t'
          f'Weak Supervision Strategy: {args.weak_supervision_strategy}\n'
          f'Uncertainty Sampling Method: {args.uncertainty_sampling_method}\t'
          f'Semi Supervised Method: {args.semi_supervised_method}\n'
          f'Dataset root: {args.root}')


def store_logs(args, acc_ratio):
    filename = '{0}-{1}-seed:{2}'.format(datetime.now().strftime("%d.%m.%Y"), args.name, args.seed)

    file = dict()
    file.update({'name': args.name})
    file.update({'time': str(datetime.now())})
    file.update({'seed': args.seed})
    file.update({'dataset': args.dataset})
    file.update({'metrics': acc_ratio})
    file.update({'other args': vars(args)})

    with open(os.path.join(args.log_path, filename), 'w') as fp:
        json.dump(file, fp, indent=4, sort_keys=True)
