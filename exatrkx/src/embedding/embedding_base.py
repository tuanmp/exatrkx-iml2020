# System imports
import sys
import os

# 3rd party imports
import numpy as np
import torch
from torch.nn import Linear
from torch.utils.data import random_split
from torch_geometric.data import DataLoader
from torch_cluster import radius_graph

import pytorch_lightning as pl
from pytorch_lightning import LightningModule
from pytorch_lightning import loggers as pl_loggers

# Local imports
from exatrkx.src import utils_torch
from exatrkx.src.utils_torch import graph_intersection

device = 'cuda' if torch.cuda.is_available() else 'cpu'
from exatrkx.src import utils_dir

def load_datasets(input_dir, train_split, seed = 0):
    '''
    Prepare the random Train, Val, Test split, using a seed for reproducibility. Seed should be
    changed across final varied runs, but can be left as default for experimentation.
    '''
    torch.manual_seed(seed)
    all_events = os.listdir(input_dir)
    all_events = sorted([os.path.join(input_dir, event) for event in all_events])
    loaded_events = [torch.load(event, map_location='cpu') for event in all_events[:sum(train_split)]]
    train_events, val_events, test_events = random_split(loaded_events, train_split)

    return train_events, val_events, test_events

class EmbeddingBase(LightningModule):

    def __init__(self, hparams):
        super().__init__()
        '''
        Initialise the Lightning Module that can scan over different embedding training regimes
        '''
        # Assign hyperparameters
        self.save_hyperparameters( hparams )
        self._set_hparams({'input_dir': utils_dir.feature_outdir})
        self._set_hparams({'output_dir': utils_dir.embedding_outdir})
        self.clustering = getattr(utils_torch, hparams['clustering'])

    def setup(self, stage):
        self.trainset, self.valset, self.testset = load_datasets(self.hparams["input_dir"], self.hparams["train_split"])


    def train_dataloader(self):
        if len(self.trainset) > 0:
            return DataLoader(self.trainset, batch_size=1, num_workers=self.hparams['n_workers'])
        else:
            return None

    def val_dataloader(self):
        if len(self.valset) > 0:
            return DataLoader(self.valset, batch_size=1, num_workers=self.hparams['n_workers'])
        else:
            return None

    def test_dataloader(self):
        if len(self.testset):
            return DataLoader(self.testset, batch_size=1, num_workers=self.hparams['n_workers'])
        else:
            return None

    def configure_optimizers(self):
        optimizer = [torch.optim.AdamW(self.parameters(), lr=(self.hparams["lr"]), betas=(0.9, 0.999), eps=1e-08, amsgrad=True)]
        scheduler = [
            {
                'scheduler': torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer[0],\
                                                    factor=self.hparams["factor"], patience=self.hparams["patience"]),
                'monitor': 'val_loss',
                'interval': 'epoch',
                'frequency': 1
            }
        ]
#         scheduler = [torch.optim.lr_scheduler.StepLR(optimizer[0], step_size=1, gamma=0.3)]
        return optimizer, scheduler

    def training_step(self, batch, batch_idx):

        # apply the embedding neural network on the hit features
        # and return hidden features in the embedding space.
        if 'ci' in self.hparams["regime"]:
            spatial = self(torch.cat([batch.cell_data, batch.x], axis=-1))
        else:
            spatial = self(batch.x)

        # create another direction for true doublets
        e_bidir = torch.cat([batch.layerless_true_edges,
                            torch.stack([batch.layerless_true_edges[1],
                                        batch.layerless_true_edges[0]], axis=1).T
                            ], axis=-1)

        # construct doublets for training
        e_spatial = torch.empty([2,0], dtype=torch.int64, device=self.device)

        if 'rp' in self.hparams["regime"]:
            # randomly select two times of total true edges
            n_random = int(self.hparams["randomisation"]*e_bidir.shape[1])
            e_spatial = torch.cat([e_spatial,
                torch.randint(e_bidir.min(), e_bidir.max(), (2, n_random), device=self.device)], axis=-1)

        # use a clustering algorithm to connect hits based on the embedding information
        # euclidean distance is used. 
        if 'hnm' in self.hparams["regime"]:
            e_spatial = torch.cat([e_spatial,
                            self.clustering(spatial, self.hparams["r_train"], self.hparams["knn_train"])], axis=-1)
            # e_spatial = torch.cat([e_spatial, 
            #         build_edges(spatial, self.hparams["r_train"], self.hparams["knn"], res)],
            #         axis=-1)
            # e_spatial = torch.cat([e_spatial,
            #                 radius_graph(spatial, r=self.hparams["r_train"], max_num_neighbors=self.hparams["knn"])], axis=-1)

        e_spatial, y_cluster = graph_intersection(e_spatial, e_bidir)

        # add all truth edges four times
        # in order to balance the number of truth and fake edges in one batch
        e_spatial = torch.cat([
            e_spatial,
            e_bidir.transpose(0,1).repeat(1,self.hparams["weight"]).view(-1, 2).transpose(0,1)
            ], axis=-1)
        y_cluster = np.concatenate([y_cluster.astype(int), np.ones(e_bidir.shape[1]*self.hparams["weight"])])

        hinge = torch.from_numpy(y_cluster).float().to(device)
        hinge[hinge == 0] = -1

        # euclidean distances in the embedding space between two hits
        reference = spatial.index_select(0, e_spatial[1])
        neighbors = spatial.index_select(0, e_spatial[0])
        d = torch.sum((reference - neighbors)**2, dim=-1)

        loss = torch.nn.functional.hinge_embedding_loss(d, hinge, margin=self.hparams["margin"], reduction="mean")

        self.log("train_loss", loss, prog_bar=True)

        return loss


    def validation_step(self, batch, batch_idx):

        if 'ci' in self.hparams["regime"]:
            spatial = self(torch.cat([batch.cell_data, batch.x], axis=-1))
        else:
            spatial = self(batch.x)

        e_bidir = torch.cat([batch.layerless_true_edges,
                               torch.stack([batch.layerless_true_edges[1], batch.layerless_true_edges[0]], axis=1).T], axis=-1)

        # use a clustering algorithm to connect hits based on the embedding information
        # euclidean distance is used. 
        e_spatial = self.clustering(spatial, self.hparams["r_val"], self.hparams["knn_val"])

        e_spatial, y_cluster = graph_intersection(e_spatial, e_bidir)

        hinge = torch.from_numpy(y_cluster).float().to(device)
        hinge[hinge == 0] = -1

        reference = spatial.index_select(0, e_spatial[1])
        neighbors = spatial.index_select(0, e_spatial[0])
        d = torch.sum((reference - neighbors)**2, dim=-1)

        val_loss = torch.nn.functional.hinge_embedding_loss(d, hinge, margin=self.hparams["margin"], reduction="mean")

        self.log("val_loss", val_loss, prog_bar=True)

        cluster_true = 2*len(batch.layerless_true_edges[0])
        cluster_true_positive = y_cluster.sum()
        cluster_positive = len(e_spatial[0])

        self.log_dict({
            'val_eff': torch.tensor(cluster_true_positive/cluster_true),
            'val_pur': torch.tensor(cluster_true_positive/cluster_positive)}, prog_bar=True)


    def optimizer_step(self, current_epoch, batch_nb, optimizer, optimizer_idx,optimizer_closure=None,
                    second_order_closure=None, on_tpu=False, using_native_amp=False, using_lbfgs=False):
        # warm up lr
        if (self.hparams["warmup"] is not None) and (self.trainer.global_step < self.hparams["warmup"]):
            lr_scale = min(1., float(self.trainer.global_step + 1) / self.hparams["warmup"])
            for pg in optimizer.param_groups:
                pg['lr'] = lr_scale * self.hparams["lr"]

        # update params
        optimizer.step(optimizer_closure)
        optimizer.zero_grad()