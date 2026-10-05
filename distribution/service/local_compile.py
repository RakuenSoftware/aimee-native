"""Retired Python model compiler. New releases use dedicated model plugins.

The prior implementation is retained under benchmarks/native_addressing/
legacy_cpu_preparation for historical research. It is excluded from releases.
"""
MESSAGE = "Use the model's dedicated vLLM plugin and Rust adapter for native preparation"

def main():
    raise RuntimeError(MESSAGE)


if __name__ == "__main__":
    main()
