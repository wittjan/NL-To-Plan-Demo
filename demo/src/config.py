import torch

import src.demo_path

from thesis_demo.config import select_backend


def backend_info():
    """Return CPU availability text, or the CUDA device name and memory."""
    backend = select_backend()
    if backend == "cpu":
        return "ONLY CPU AVAILABLE"
    if backend == "cuda":
        device_name = torch.cuda.get_device_name(0)
        memory_gb = torch.cuda.get_device_properties(0).total_memory // (1024**3)
        return f"NVIDIA: {device_name} ({memory_gb} GB)"
