"""
Model Registry - ONNX Model Management with VRAM Capping

Registry that loads lightweight ONNX models (XGBoost, LightGBM, quantized
tiny-Transformers) into GPU/NPU memory, strictly capping VRAM usage to 4GB.

Implements LRU eviction when memory limit is approached.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from collections import OrderedDict
import threading
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelInfo:
    """Information about a loaded model"""
    
    def __init__(self, name: str, path: str, size_mb: float, session: Any):
        self.name = name
        self.path = path
        self.size_mb = size_mb
        self.session = session
        self.access_count = 0
        self.last_access_time = 0.0
    
    def touch(self):
        """Update access time and count"""
        import time
        self.access_count += 1
        self.last_access_time = time.time()


class ModelRegistry:
    """
    Registry for managing ONNX models with strict memory limits.
    Implements LRU eviction to stay within 4GB VRAM cap.
    """
    
    _instance: Optional['ModelRegistry'] = None
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
        self.models: OrderedDict[str, ModelInfo] = OrderedDict()
        self.vram_cap_mb = 4096  # 4GB VRAM cap
        self.current_vram_usage_mb = 0.0
        self.model_metadata: Dict[str, Dict] = {}
        
        logger.info(f"ModelRegistry initialized with {self.vram_cap_mb}MB VRAM cap")
    
    def register_model(
        self,
        name: str,
        model_path: str,
        execution_providers: List[str],
        session_options: Optional[Any] = None,
    ) -> Optional[Any]:
        """
        Register and load an ONNX model into the registry.
        
        Args:
            name: Unique identifier for the model
            model_path: Path to the ONNX model file
            execution_providers: List of execution providers (e.g., ['DirectMLExecutionProvider'])
            session_options: ONNX Runtime session options
            
        Returns:
            Loaded ONNX session or None if loading failed
        """
        try:
            import onnxruntime as ort
            
            # Check if already loaded
            if name in self.models:
                logger.info(f"Model '{name}' already loaded, returning cached session")
                return self.models[name].session
            
            # Get model file size
            model_size_mb = self._get_file_size_mb(model_path)
            
            # Check if we have enough memory
            if not self._can_fit_model(model_size_mb):
                logger.warning(f"Not enough VRAM for '{name}' ({model_size_mb}MB), evicting...")
                self._evict_models(model_size_mb)
            
            # Load the model
            session = ort.InferenceSession(
                model_path,
                sess_options=session_options,
                providers=execution_providers,
            )
            
            # Store in registry
            model_info = ModelInfo(name, model_path, model_size_mb, session)
            self.models[name] = model_info
            self.current_vram_usage_mb += model_size_mb
            
            # Store metadata
            self.model_metadata[name] = {
                "input_names": [inp.name for inp in session.get_inputs()],
                "output_names": [out.name for out in session.get_outputs()],
                "input_shapes": [inp.shape for inp in session.get_inputs()],
            }
            
            logger.info(f"Loaded model '{name}' ({model_size_mb:.1f}MB), VRAM usage: {self.current_vram_usage_mb:.1f}/{self.vram_cap_mb}MB")
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to load model '{name}': {e}")
            return None
    
    def get_model(self, name: str) -> Optional[Any]:
        """Get a loaded model session by name"""
        if name not in self.models:
            logger.warning(f"Model '{name}' not found in registry")
            return None
        
        # Update access tracking
        model_info = self.models[name]
        model_info.touch()
        
        # Move to end (most recently used)
        self.models.move_to_end(name)
        
        return model_info.session
    
    def unload_model(self, name: str) -> bool:
        """Unload a specific model from the registry"""
        if name not in self.models:
            return False
        
        model_info = self.models.pop(name)
        self.current_vram_usage_mb -= model_info.size_mb
        
        # Delete session to free memory
        del model_info.session
        
        logger.info(f"Unloaded model '{name}', VRAM usage: {self.current_vram_usage_mb:.1f}/{self.vram_cap_mb}MB")
        return True
    
    def unload_all(self):
        """Unload all models from the registry"""
        for name in list(self.models.keys()):
            self.unload_model(name)
        logger.info("All models unloaded")
    
    def get_model_metadata(self, name: str) -> Optional[Dict]:
        """Get metadata for a loaded model"""
        return self.model_metadata.get(name)
    
    def get_vram_usage(self) -> Tuple[float, float]:
        """Get current and capped VRAM usage"""
        return self.current_vram_usage_mb, self.vram_cap_mb
    
    def get_loaded_models(self) -> List[str]:
        """Get list of currently loaded model names"""
        return list(self.models.keys())
    
    def _get_file_size_mb(self, path: str) -> float:
        """Get file size in MB"""
        try:
            return Path(path).stat().st_size / (1024 * 1024)
        except Exception:
            return 50.0  # Default estimate
    
    def _can_fit_model(self, model_size_mb: float) -> bool:
        """Check if a model can fit in remaining VRAM"""
        overhead = model_size_mb * 0.5  # 50% overhead for activations
        total_needed = model_size_mb + overhead
        return (self.current_vram_usage_mb + total_needed) <= self.vram_cap_mb
    
    def _evict_models(self, needed_mb: float):
        """Evict least recently used models until we have enough space"""
        overhead = needed_mb * 0.5
        total_needed = needed_mb + overhead
        
        while (self.current_vram_usage_mb + total_needed) > self.vram_cap_mb:
            if not self.models:
                logger.warning("No more models to evict, may run out of VRAM")
                break
            
            # Evict least recently used (first item in OrderedDict)
            lru_name = next(iter(self.models))
            self.unload_model(lru_name)
            logger.info(f"Evicted LRU model '{lru_name}'")
    
    def preload_models(
        self,
        model_configs: List[Dict[str, Any]],
        execution_providers: List[str],
        session_options: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Preload multiple models based on configuration.
        
        Args:
            model_configs: List of dicts with 'name' and 'path' keys
            execution_providers: Execution providers to use
            session_options: Session options
            
        Returns:
            Dict mapping model names to sessions
        """
        loaded = {}
        
        for config in model_configs:
            name = config.get('name')
            path = config.get('path')
            
            if not name or not path:
                logger.warning(f"Invalid model config: {config}")
                continue
            
            session = self.register_model(
                name=name,
                model_path=path,
                execution_providers=execution_providers,
                session_options=session_options,
            )
            
            if session:
                loaded[name] = session
        
        return loaded
    
    def get_status(self) -> Dict[str, Any]:
        """Get registry status for monitoring"""
        return {
            "vram_used_mb": round(self.current_vram_usage_mb, 2),
            "vram_cap_mb": self.vram_cap_mb,
            "vram_utilization_pct": round((self.current_vram_usage_mb / self.vram_cap_mb) * 100, 2),
            "loaded_models": len(self.models),
            "models": [
                {
                    "name": info.name,
                    "size_mb": round(info.size_mb, 2),
                    "access_count": info.access_count,
                }
                for info in self.models.values()
            ],
        }


# Singleton accessor
def get_model_registry() -> ModelRegistry:
    """Get the singleton ModelRegistry instance"""
    return ModelRegistry()


# Convenience functions
def load_model(name: str, path: str) -> Optional[Any]:
    """Load a model with default settings"""
    from ml.hardware_accelerator import get_hardware_accelerator
    
    accelerator = get_hardware_accelerator()
    registry = get_model_registry()
    
    return registry.register_model(
        name=name,
        model_path=path,
        execution_providers=accelerator.get_execution_providers(),
        session_options=accelerator.get_session_options(),
    )


def get_model(name: str) -> Optional[Any]:
    """Get a loaded model"""
    return get_model_registry().get_model(name)
