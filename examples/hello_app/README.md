# hello_app — example for CodeShield

A minimal Python program that exposes a `secret_algorithm` function. It
serves as a target for demonstrating the full protection pipeline.

## Run it directly

```
python examples/hello_app/main.py 100
```

## Build a protected executable

From the repository root, after `pip install -e .[dev]`:

```
codeshield build examples/hello_app main.py --name hello
```

This will:

1. Obfuscate `main.py` with PyArmor into `build/obfuscated/`.
2. Compute a SHA-256 integrity manifest at `build/obfuscated/integrity.json`.
3. Package the obfuscated entry script into a single-file executable
   under `dist/`.

Run the resulting binary:

* Linux/macOS: `./dist/hello 100`
* Windows: `dist\hello.exe 100`

## Verify integrity manually

```
codeshield verify build/obfuscated build/obfuscated/integrity.json
```

If any file in the obfuscated tree is added, removed, or modified, this
exits non-zero with a message naming the offending file.
