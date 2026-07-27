#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

detect_cuda_index() {
  if [ -n "${CUDA_INDEX:-}" ]; then echo "${CUDA_INDEX}"; return; fi
  if ! command -v nvidia-smi >/dev/null 2>&1; then echo "cu126"; return; fi

  # The CUDA runtime version supported by the driver, shown in the nvidia-smi
  # header (e.g. "CUDA Version: 12.2"). This is the max CUDA version the wheel
  # may target -- NOT the driver_version (e.g. 535.104.05).
  local cuda major minor
  cuda="$(nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | head -n1 | grep -oE '[0-9]+\.[0-9]+')"
  major="${cuda%%.*}"
  minor="${cuda#*.}"; minor="${minor%%.*}"

  # Pick the highest PyTorch wheel index whose CUDA version is <= the driver's.
  case "${major}" in
    11) echo "cu118" ;;
    12)
      if   [ "${minor:-0}" -ge 8 ]; then echo "cu128"
      elif [ "${minor:-0}" -ge 6 ]; then echo "cu126"
      elif [ "${minor:-0}" -ge 4 ]; then echo "cu124"
      else echo "cu121"
      fi
      ;;
    13) echo "cu128" ;;
    *) echo "cu126" ;;
  esac
}

if command -v nvidia-smi >/dev/null 2>&1; then
  PROFILE=nvidia
else
  PROFILE=cpu
fi

echo "Detected backend: ${PROFILE}"

if [ "${PROFILE}" = "nvidia" ]; then
  CUDA_INDEX="$(detect_cuda_index)"
  export CUDA_INDEX
  echo "CUDA driver -> PyTorch wheel index: ${CUDA_INDEX}"
  echo "(override with: CUDA_INDEX=cu124 ./run.sh)"
fi

exec docker compose --profile "${PROFILE}" up --build
