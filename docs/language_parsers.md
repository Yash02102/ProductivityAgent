# Language Parser CLI Reference

This document describes the language-specific analyzers that live under `language_parsers/`. These small CLI tools normalise source code structure into a JSON contract that the Python impact analyzer can consume.

## Common Contract

Every parser is expected to behave as a command line program with the following characteristics:

- **Input** – Entire file contents provided via STDIN (preferred) or via a single file path argument (`parser.exe -` or `parser.exe path/to/File`).
- **Output** – UTF-8 JSON written to STDOUT. The top-level payload is a list of symbol entries; each entry must contain:
  - `Type` / `Kind` – High level category (class, method, namespace, etc.).
  - `Name` / `Identifier` – Unqualified symbol name.
  - `QualifiedName` – Namespace + container + name.
  - `DisplayName` / `Signature` – Human-friendly label (often matches IDE signature).
  - `Namespace` / `NamespaceName` – Optional logical namespace.
  - `StartLine`/`EndLine` and optional `StartColumn`/`EndColumn` – 1-based source span.

The JSON schema mirrors the fields produced by the Roslyn C# analyzer today. Additional keys are allowed, but the fields above must be present.

Parsers should exit with code `0` for success and non-zero for unexpected failures. Error details can be written to STDERR; downstream callers ignore STDERR but log it for troubleshooting.

## C# Parser (`language_parsers/csharp`)

### Purpose

Turns C# source files into structured symbol data using Roslyn. The result helps the Python impact analyzer group changes by namespaces, classes, and members.

### Build

```
dotnet build language_parsers/csharp/CSharpCodeParser.csproj -c Debug
```

The debug build emits `bin/Debug/net8.0/CSharpCodeParser.dll`. Release builds are also supported and live under `bin/Release/net8.0/`.

### Usage

```
# From project root
dotnet language_parsers/csharp/bin/Debug/net8.0/CSharpCodeParser.dll - < MyFile.cs
# or
dotnet language_parsers/csharp/bin/Debug/net8.0/CSharpCodeParser.dll MyFile.cs
```

### Behaviour

1. Reads input (STDIN or file path).
2. Parses syntax with the latest C# language version.
3. Builds a Roslyn compilation with framework references discovered from the runtime (`TRUSTED_PLATFORM_ASSEMBLIES`).
4. Walks all syntax nodes, collecting declared symbols (namespaces, types, members) with valid source locations.
5. Emits a JSON array of `SymbolDto` objects. Example output:

```json
[
  {
    "Type": "namespace",
    "Kind": "namespace",
    "Name": "MyNamespace",
    "QualifiedName": "Company.Product.MyNamespace",
    "DisplayName": "Company.Product.MyNamespace",
    "Signature": "Company.Product.MyNamespace",
    "Namespace": "Company.Product",
    "StartLine": 1,
    "EndLine": 42,
    "StartColumn": 1,
    "EndColumn": 2
  },
  {
    "Type": "class",
    "Kind": "class",
    "Name": "OrderService",
    "QualifiedName": "Company.Product.MyNamespace.OrderService",
    "DisplayName": "OrderService",
    "Signature": "Company.Product.MyNamespace.OrderService",
    "Namespace": "Company.Product.MyNamespace",
    "StartLine": 5,
    "EndLine": 38,
    "StartColumn": 5,
    "EndColumn": 6
  }
]
```

### Integration Points

- `app/config.py` automatically resolves `settings.cs_code_analyzer` to the built DLL if present.
- `app/services/code_analyzer/cs_code_analyzer.py` shells out to the DLL via `dotnet`, reads STDOUT, and converts it to the generic Python contract consumed by the impact analyzer.

## Adding More Parsers

1. Create a new subfolder under `language_parsers/` (e.g., `python`, `typescript`).
2. Implement a CLI that follows the contract above. Use language specific tooling (e.g., `ast` for Python, `ts-morph`/`typescript` compiler API for TS).
3. Update `app/config.py` to prefer the new parser when the corresponding file extension is analysed.
4. Extend `ImpactAnalyzer.get_handler` to map the file extension to the new analyzer.
5. Document usage in this file to keep parity across languages.

## Troubleshooting

- **Empty Output** – Usually indicates the parser couldn’t find any symbols. Check STDERR for hints and ensure the input uses supported syntax.
- **`dotnet` command missing** – Install the .NET SDK 8.0+ to build and run the C# parser.
- **Incorrect paths** – Rebuild the parser so `bin/Debug` or `bin/Release` folders exist, or override `CS_CODE_ANALYZER` in `.env` with an absolute path.
