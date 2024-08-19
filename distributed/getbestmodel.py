#!/usr/bin/env python3

import os
import json
import yaml
import argparse
import glob

import wandb
import numpy as np
import h5py
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset


def test(config, test, model):

    # model evaluation hyperparameters
    batch_size = config['batch_size']

    # set to eval mode
    model.eval()

    # validation
    dataset = TensorDataset(test['x'], test['y'])
    loader = DataLoader(dataset=dataset, batch_size=256)
    criterion = nn.BCELoss()

    # set device (cuda or cpu)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    criterion.to(device)

    with torch.no_grad():
        loss = 0.0
        for sequences, target in loader:
            sequences = sequences.to(device)
            target = target.to(device).float()
            outputs = model(sequences)
            loss += criterion(outputs.squeeze(), target)
        loss /= len(loader.dataset)
        print(f'test loss: {loss}\n')

    return loss

if __name__ == '__main__':

    # retrieve arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('config_pathname', type=str)
    parser.add_argument('output_pathname', type=str)
    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # load in wandb info
    with open(os.path.join(script_dir, args.config_pathname), 'r') as file:
        config = yaml.safe_load(file)

    # login to wandb
    os.environ['WANDB_API_KEY'] = config['wandb']['api_key']
    os.environ['WANDB_ENTITY'] = config['wandb']['entity']
    os.environ['WANDB_PROJECT'] = config['wandb']['project']
    wandb.login()

    # retrieve best run_id
    sweep = wandb.Api().sweep(f"{config['wandb']['entity']}/{config['wandb']['project']}/{config['wandb']['sweep_id']}")
    best_run = min(sweep.runs, key=lambda run: run.summary.get('f-measure', float('inf')))

    # copy HDF5 file to input directory of FINAL NODE
    file_pattern = os.path.join(script_dir, f"{best_run.config['run_prefix']}-*.h5")
    h5_pathname = matching_files = glob.glob(file_pattern)[0]
    with h5py.File(h5_pathname, 'r') as h5f:
        dataset = h5f['test'][:]
        x = torch.as_tensor(dataset['timeseries'].copy())
        y = torch.as_tensor(dataset['label'].copy())

    # load in best model
    matching_files = glob.glob(os.path.join(script_dir, f"{best_run.config['run_prefix']}-*.pt"))
    model_pathname = matching_files[0]
    model = torch.jit.load(model_pathname)

    # resume run in wandb to fetch training hyperparameters for test evaluation
    with wandb.init(resume='must', id=best_run.id) as run:
        test_loss = test(run.config, {'x':x, 'y':y}, model)
        with open(os.path.join(script_dir, args.output_pathname), 'w') as outf:
            outf.write(model_pathname + '\n')
            outf.write(f'test_loss: {test_loss}' + '\n')
