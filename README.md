# Tracking-ML-Exa.TrkX
Building input graphs for Graph Neural Network (GNN) is based on the embedding learning and filtering with multilayer perceptrons, both of which are implemented in [Pytorch](https://pytorch.org/get-started/locally/). The GNN is implemented in the TensorFlow with the [graph_nets](https://github.com/deepmind/graph_nets) package.

To quickly get started, you can visit our [walk-through notebook](https://github.com/exatrkx/exatrkx-iml2020/blob/main/notebooks/WalkThroughGNN4Tracking.ipynb).
<!-- [Documentation available here.](https://hsf-reco-and-software-triggers.github.io/Tracking-ML-Exa.TrkX/) -->
## Installation

```bash
conda create --name exatrkx python=3.8 pytorch torchvision torchaudio faiss-gpu cudatoolkit=11.3 matplotlib jupyter -c pytorch

conda activate exatrkx

pip install --upgrade pip

pip install -e .

pip install pytorch_lightning tensorflow graph_nets
```
Dependencies not listed in the `setup.py` are tabulated below. We are referring to their webpage for detailed installation instructions.

* [pytorch](https://pytorch.org/get-started/locally/) for embedding learning and filtering
* [torch-geometric](https://github.com/rusty1s/pytorch_geometric#installation) for GNN in Pytorch
* [tensorflow](https://www.tensorflow.org/install) for GNN in TensorFlow
* [mpi4py](https://mpi4py.readthedocs.io/en/stable/install.html) for distributed training
* [horovod](https://github.com/horovod/horovod#install) for distributed training

We prepared a script to install the `torch-geometric`, which can be executed as `install_geometric.sh cu113 1.11.0` where the first argument `cu113` is the CUDA version and the second is the `pytorch` version.

You can find out the cuda and pytorch version by running 

```
python -c "import torch; print(torch.__version__, torch.version.cuda)"
```
and then run 
```
export $CUDA_VERSION="your-cuda-version"
export $TORCH_VERSION="your-torch-version"
install_geometric.sh $CUDA_VERSION $TORCH_VERSION
```
where the cuda version must be in cu1xx format.

## Pipelines
The program saves intermediate files after each processing step and we organize those outputs with a predefined structure. **Users have to assign two environment variables**: `TRKXINPUTDIR` for tracking input data pointing to the csv files for each event and the `detector.csv` file should be at its uplevel folder; `TRKXOUTPUTDIR` for saving output files. It can be done either in bash via `export TRKXINPUTDIR=my-input-dir` and `export TRKXOUTPUTDIR=my-output-dir` or in python script via 
```python
import os
os.environ['TRKXINPUTDIR'] = "my-input-dir"
os.environ['TRKXOUTPUTDIR'] = "my-output-dir"
```

### Preprocessing
It reads input files, constructs cell features and more importantly figures out truth connections (edges) between hits from the same track.
```run_lightning.py --action build```

### Embedding
It uses the hit position and cell information as inputs and embeds each hit into a hidden phasespace where hits from the same track are clustered together. If the option `--config` is missing the default configuration will be used.
```run_lightning.py --action embedding --config train_embedding.yaml  --gpus 1 --max_epochs 10```

### Filtering
It uses multilayer percetrons to filter out as much fake edges as possible while keeping a high efficiency.
```run_lightning.py --action filtering --config train_filter.yaml --gpus 1 --max_epochs 10```

### Convert to TF graph
```convert2tf.py```

### Train GNN
```train_gnn_tf.py --max-epochs 10```

### Evaluate GNN
```eval_gnn_tf.py```

### Track labeling
```tracks_from_gnn.py```
