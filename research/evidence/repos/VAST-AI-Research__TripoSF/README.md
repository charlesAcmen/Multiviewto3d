# TripoSF: High-Resolution and Arbitrary-Topology 3D Shape Modeling with SparseFlex

<div align="center">

[![Project Page](https://img.shields.io/badge/🏠-Project%20Page-blue.svg)](https://XianglongHe.github.io/TripoSF/index.html)
[![Paper](https://img.shields.io/badge/📑-Paper-green.svg)](https://arxiv.org/abs/2503.21732)
[![Model](https://img.shields.io/badge/🤗-Model-yellow.svg)](https://huggingface.co/VAST-AI/TripoSF)

**By [Tripo](https://www.tripo3d.ai)**

</div>

![teaser](assets/docs/teaser.png)

## 🌟 Overview

TripoSF represents a significant leap forward in 3D shape modeling, combining high-resolution capabilities with arbitrary topology support. Our approach enables:

- 📈 Ultra-high resolution mesh modeling (up to $1024^3$)
- 🎯 Direct optimization from rendering losses
- 🌐 Efficient handling of open surfaces and complex topologies
- 💾 Dramatic memory reduction through sparse computation
- 🔄 Differentiable mesh extraction with sharp features

### SparseFlex

SparseFlex, the core design powering TripoSF, introduces a sparse voxel structure that:
- Focuses computational resources only on surface-adjacent regions
- Enables natural handling of open surfaces (like cloth or leaves)
- Supports complex internal structures without compromises
- Achieves massive memory reduction compared to dense representations

## 🔥 Updates

* [2025-03] Initial Release:
  - Pretrained VAE model weights ($1024^3$ reconstruction)
  - Inference scripts and examples
  - SparseFlex implementation

## 🚀 Getting Started

### System Requirements
- CUDA-capable GPU (≥12GB VRAM for $1024^3$ resolution)
- PyTorch 2.0+

### Installation

1. Clone the repository:
```bash
git clone https://github.com/VAST-AI-Research/TripoSF.git
cd TripoSF
```

2. Install dependencies:
```bash
# Install PyTorch (select the correct CUDA version)
pip install torch torchvision --index-url https://download.pytorch.org/whl/{your-cuda-version}

# Install other dependencies
pip install -r requirements.txt
```

## 💫 Usage

### Pretrained Model Setup
1. Download our pretrained models from [Hugging Face](https://huggingface.co/VAST-AI/TripoSF)
2. Place the models in the `ckpts/` directory

### Running Inference
Basic reconstruction using TripoSFVAE:
```bash
python inference.py --mesh-path "assets/examples/jacket.obj" \
                   --output-dir "outputs/" \
                   --config "configs/TripoSFVAE_1024.yaml"
```

### Local Gradio Example
```bash
python app.py
```
![gradio_example](assets/docs/local_gradio_example.png)

### Optimization Tips 💡

#### For Open Surfaces
- Enable `pruning` in the configuration:
  ```yaml
  pruning: true
  ```
- Benefits:
  - Higher-fidelity reconstruction
  - Faster processing
  - Better memory efficiency

#### For Complex Shapes
- Increase sampling density:
  ```yaml
  sample_points_num: 1638400  # Default: 819200
  ```
- Adjust resolution based on detail requirements:
  ```yaml
  resolution: 1024  # Options: 256, 512, 1024
  ```


## 📊 Technical Details

TripoSF VAE Architecture:
- **Input**: Point clouds (preserving source geometry details)
- **Encoder**: Sparse transformer for efficient geometry encoding
- **Decoder**: Self-pruning upsampling modules maintaining sparsity
- **Output**: High-resolution SparseFlex parameters for mesh extraction

## 📝 Citation

```bibtex
@article{he2025triposf,
  title={SparseFlex: High-Resolution and Arbitrary-Topology 3D Shape Modeling},
  author={He, Xianglong and Zou, Zi-Xin and Chen, Chia-Hao and Guo, Yuan-Chen and Liang, Ding and Yuan, Chun and Ouyang, Wanli and Cao, Yan-Pei and Li, Yangguang},
  journal={arXiv preprint arXiv:2503.21732},
  year={2025}
}
```


## 📚 Acknowledgements

Our work builds upon these excellent repositories:
- [Trellis](https://github.com/Microsoft/TRELLIS)
- [Flexicubes](https://github.com/MaxtirError/FlexiCubes)

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
