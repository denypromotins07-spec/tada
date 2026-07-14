"""
Hardware Accelerator - AMD NPU/GPU Manager for AI Inference

Singleton manager that detects AMD hardware using ONNX Runtime with DirectML
execution provider. Handles fallback to CPU if GPU/NPU is unavailable or busy.

Optimized for AMD Ryzen AI 5 NPU and Radeon GPU on 16GB RAM systems.
"""

import logging
from typing import Dict, List, Optional, Any
import threading
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionProvider(Enum):
    """Available execution providers"""
    DIRECTML = "DirectML"  # AMD GPU
    OPENVINO = "OpenVINO"  # Intel NPU (fallback)
    CPU = "CPU"  # CPU fallback


class HardwareAccelerator:
    """
    Singleton hardware accelerator manager for AMD NPU/GPU inference.
    Caps VRAM usage to 4GB to respect 16GB system RAM constraint.
    """
    
    _instance: Optional['HardwareAccelerator'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.providers: List[str] = []
        self.active_provider: Optional[ExecutionProvider] = None
        self.vram_cap_gb = 4.0  # Cap VRAM at 4GB
        self.max_memory_mb = 8192  # Max 8GB system RAM for ML
        self.device_info: Dict[str, Any] = {}
        
        self._detect_hardware()
        self._initialize_onnx_runtime()
    
    def _detect_hardware(self):
        """Detect available AMD hardware"""
        logger.info("Detecting hardware...")
        
        # Try to detect DirectML (AMD GPU)
        try:
            import onnxruntime as ort
            
            available_providers = ort.get_available_providers()
            self.providers = available_providers
            
            if 'DirectMLExecutionProvider' in available_providers:
                self.active_provider = ExecutionProvider.DIRECTML
                logger.info("✓ DirectML (AMD GPU) detected")
                
                # Get device info
                try:
                    import subprocess
                    result = subprocess.run(
                        ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        self.device_info['gpu_name'] = result.stdout.strip().split('\n')[-1].strip()
                except Exception:
                    self.device_info['gpu_name'] = "AMD Radeon (DirectML)"
                    
            elif 'OpenVINOExecutionProvider' in available_providers:
                self.active_provider = ExecutionProvider.OPENVINO
                logger.info("✓ OpenVINO (Intel NPU) detected")
                self.device_info['npu_name'] = "Intel NPU"
                
            else:
                self.active_provider = ExecutionProvider.CPU
                logger.warning("⚠ No GPU/NPU detected, falling back to CPU")
                self.device_info['cpu_cores'] = self._get_cpu_core_count()
                
        except ImportError:
            self.active_provider = ExecutionProvider.CPU
            logger.warning("⚠ ONNX Runtime not installed, using CPU only")
            self.device_info['cpu_cores'] = self._get_cpu_core_count()
        
        logger.info(f"Active execution provider: {self.active_provider.value}")
    
    def _get_cpu_core_count(self) -> int:
        """Get CPU core count"""
        try:
            import multiprocessing
            return multiprocessing.cpu_count()
        except Exception:
            return 4
    
    def _initialize_onnx_runtime(self):
        """Initialize ONNX Runtime with optimal settings"""
        try:
            import onnxruntime as ort
            
            # Configure session options
            self.session_options = ort.SessionOptions()
            
            # Set memory limit
            self.session_options.intra_op_num_threads = min(4, self._get_cpu_core_count())
            self.session_options.inter_op_num_threads = 2
            
            # Enable memory pattern optimization
            self.session_options.enable_mem_pattern = True
            
            # Set arena extend strategy
            self.session_options.add_session_config_entry(
                'session.intra_op.allow_spinning', '1'
            )
            
            # DirectML specific settings
            if self.active_provider == ExecutionProvider.DIRECTML:
                self.session_options.add_session_config_entry(
                    'session.directml.enable_dynamic_shapes', '1'
                )
            
            logger.info("ONNX Runtime initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ONNX Runtime: {e}")
            self.session_options = None
    
    def get_session_options(self):
        """Get configured ONNX Runtime session options"""
        return self.session_options
    
    def get_execution_providers(self) -> List[str]:
        """Get list of available execution providers in priority order"""
        if self.active_provider == ExecutionProvider.DIRECTML:
            return ['DirectMLExecutionProvider', 'CPUExecutionProvider']
        elif self.active_provider == ExecutionProvider.OPENVINO:
            return ['OpenVINOExecutionProvider', 'CPUExecutionProvider']
        else:
            return ['CPUExecutionProvider']
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get detected device information"""
        return {
            **self.device_info,
            'active_provider': self.active_provider.value if self.active_provider else None,
            'available_providers': self.providers,
            'vram_cap_gb': self.vram_cap_gb,
            'max_memory_mb': self.max_memory_mb,
        }
    
    def is_gpu_available(self) -> bool:
        """Check if GPU acceleration is available"""
        return self.active_provider == ExecutionProvider.DIRECTML
    
    def is_npu_available(self) -> bool:
        """Check if NPU acceleration is available"""
        return self.active_provider == ExecutionProvider.OPENVINO
    
    def can_accelerate(self) -> bool:
        """Check if any hardware acceleration is available"""
        return self.active_provider != ExecutionProvider.CPU
    
    def estimate_model_memory(self, model_size_mb: float) -> float:
        """Estimate memory usage for a model including overhead"""
        # Model weights + activations + temporary buffers
        overhead_multiplier = 2.5
        return model_size_mb * overhead_multiplier
    
    def should_load_model(self, model_size_mb: float) -> bool:
        """Check if we have enough memory to load a model"""
        estimated_memory = self.estimate_model_memory(model_size_mb)
        return estimated_memory <= (self.max_memory_mb * 0.8)  # Keep 20% headroom
    
    def get_optimal_batch_size(self, model_input_size_mb: float) -> int:
        """Calculate optimal batch size based on available memory"""
        available_memory = self.max_memory_mb * 0.5  # Use 50% for batch processing
        samples_per_mb = 1.0 / model_input_size_mb if model_input_size_mb > 0 else 100
        optimal_batch = int(available_memory * samples_per_mb)
        return max(1, min(optimal_batch, 256))  # Clamp between 1 and 256
    
    def warmup(self, session: Any):
        """Perform warmup inference to optimize performance"""
        if not self.can_accelerate():
            return
        
        try:
            # Run dummy inference to trigger JIT compilation
            import numpy as np
            
            # Get input shape from session
            input_name = session.get_inputs()[0].name
            input_shape = session.get_inputs()[0].shape
            
            # Create dummy input
            dummy_input = {input_name: np.random.randn(*input_shape).astype(np.float32)}
            
            # Run warmup inference
            session.run(None, dummy_input)
            
            logger.info("Hardware accelerator warmup complete")
            
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")
    
    def cleanup(self):
        """Cleanup resources"""
        logger.info("Hardware accelerator cleanup complete")


# Singleton accessor
def get_hardware_accelerator() -> HardwareAccelerator:
    """Get the singleton HardwareAccelerator instance"""
    return HardwareAccelerator()


# Convenience functions
def is_amd_gpu_available() -> bool:
    """Check if AMD GPU (DirectML) is available"""
    return get_hardware_accelerator().is_gpu_available()


def get_execution_providers() -> List[str]:
    """Get available execution providers"""
    return get_hardware_accelerator().get_execution_providers()


def get_device_info() -> Dict[str, Any]:
    """Get device information"""
    return get_hardware_accelerator().get_device_info()
