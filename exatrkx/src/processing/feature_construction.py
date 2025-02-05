# System imports
import sys
import os
import multiprocessing as mp
from functools import partial
import glob

# 3rd party imports
import numpy as np
import pytorch_lightning as pl
from pytorch_lightning import LightningDataModule
from torch.nn import Linear
import torch.nn as nn

# Local imports
from .utils.event_utils import prepare_event
from .utils.detector_utils import load_detector
from exatrkx.src import utils_dir

class FeatureStore(LightningDataModule):

    def __init__(self, hparams):
        super().__init__()
        self.save_hyperparameters(hparams)

        self.input_dir = utils_dir.inputdir
        self._set_hparams({'input_dir': utils_dir.inputdir}) 
        
        self.output_dir = utils_dir.feature_outdir
        self._set_hparams({'output_dir': self.output_dir})
        self.detector_path = utils_dir.detector_path
        self.n_files = self.hparams['n_files']

        self.n_tasks = self.hparams['n_tasks']
        self.task = 0 if "task" not in self.hparams else self.hparams['task']
        self.n_workers = self.hparams['n_workers'] if "n_workers" in self.hparams else len(os.sched_getaffinity(0))
        self.build_weights = self.hparams['build_weights'] if 'build_weights' in self.hparams else True
        self.show_progress = self.hparams['show_progress'] if 'show_progress' in self.hparams else True

    def prepare_data(self):
        # Find the input files
        # all_files = os.listdir(self.input_dir)
        # print(self.input_dir)
        all_files = [os.path.basename(x) for x in glob.glob(os.path.join(self.input_dir, "*.csv"))]
        all_events = sorted(np.unique([os.path.join(self.input_dir, event[:14]) for event in all_files]))[:self.n_files]

        # Split the input files by number of tasks and select my chunk only
        all_events = np.array_split(all_events, self.n_tasks)[self.task]
        print(all_events)

        # Define the cell features to be added to the dataset

        cell_features = ['cell_count', 'cell_val', 'leta', 'lphi', 'lx', 'ly', 'lz', 'geta', 'gphi']
        detector_orig, detector_proc = load_detector(self.detector_path)

        # Prepare output
        # output_dir = os.path.expandvars(self.output_dir) FIGURE OUT HOW TO USE THIS!
        os.makedirs(self.output_dir, exist_ok=True)
        print('Writing outputs to ' + self.output_dir)

        # Process input files with a worker pool
        with mp.Pool(processes=self.n_workers) as pool:
            process_func = partial(prepare_event, detector_orig=detector_orig, detector_proc=detector_proc,
                                cell_features=cell_features, **self.hparams)
            pool.map(process_func, all_events)