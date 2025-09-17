using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Text;

namespace CSharpCodeParser;

internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public static int Main(string[] args)
    {
        try
        {
            var source = ReadSource(args);
            var payload = Analyzer.Analyze(source);
            Console.OutputEncoding = Encoding.UTF8;
            Console.Write(JsonSerializer.Serialize(payload, JsonOptions));
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            Console.Write("[]");
        }

        return 0;
    }

    private static string ReadSource(string[] args)
    {
        if (args.Length > 0 && args[0] != "-")
        {
            var path = args[0];
            if (File.Exists(path))
            {
                return File.ReadAllText(path);
            }
        }

        using var reader = new StreamReader(Console.OpenStandardInput());
        return reader.ReadToEnd();
    }
}

internal static class Analyzer
{
    public static IReadOnlyList<SymbolDto> Analyze(string? source)
    {
        if (string.IsNullOrWhiteSpace(source))
        {
            return Array.Empty<SymbolDto>();
        }

        try
        {
            var parseOptions = CSharpParseOptions.Default.WithLanguageVersion(LanguageVersion.Latest);
            var syntaxTree = CSharpSyntaxTree.ParseText(source, parseOptions);
            var compilation = CSharpCompilation.Create(
                "Analyzer",
                new[] { syntaxTree },
                ReferenceCache.References,
                new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

            var semanticModel = compilation.GetSemanticModel(syntaxTree);
            var root = syntaxTree.GetRoot();
            var symbols = new List<SymbolDto>();
            var seen = new HashSet<(string? name, TextSpan span)>();

            foreach (var node in root.DescendantNodesAndSelf())
            {
                var symbol = semanticModel.GetDeclaredSymbol(node);
                if (symbol is null || symbol.IsImplicitlyDeclared)
                {
                    continue;
                }

                var typeLabel = SymbolMapper.MapKind(symbol);
                if (typeLabel is null)
                {
                    continue;
                }

                if (!symbol.Locations.Any(loc => loc.IsInSource))
                {
                    continue;
                }

                var lineSpan = node.GetLocation().GetLineSpan();
                if (!lineSpan.IsValid)
                {
                    continue;
                }

                var key = (symbol.Name, node.Span);
                if (!seen.Add(key))
                {
                    continue;
                }

                var dto = SymbolMapper.ToDto(symbol, lineSpan);
                dto.Type = typeLabel;
                dto.Kind = typeLabel;
                symbols.Add(dto);
            }

            return symbols;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex);
            return Array.Empty<SymbolDto>();
        }
    }
}

file static class ReferenceCache
{
    private static readonly Lazy<IReadOnlyList<MetadataReference>> LazyReferences = new(Build);

    public static IReadOnlyList<MetadataReference> References => LazyReferences.Value;

    private static IReadOnlyList<MetadataReference> Build()
    {
        var list = new List<MetadataReference>();
        if (AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") is string tpa)
        {
            foreach (var path in tpa.Split(Path.PathSeparator))
            {
                if (string.IsNullOrWhiteSpace(path))
                {
                    continue;
                }

                try
                {
                    list.Add(MetadataReference.CreateFromFile(path));
                }
                catch
                {
                    // ignore reference load errors
                }
            }
        }

        return list;
    }
}

internal static class SymbolMapper
{
    private static readonly SymbolDisplayFormat QualifiedFormat = new(
        globalNamespaceStyle: SymbolDisplayGlobalNamespaceStyle.Omitted,
        typeQualificationStyle: SymbolDisplayTypeQualificationStyle.NameAndContainingTypesAndNamespaces,
        genericsOptions: SymbolDisplayGenericsOptions.IncludeTypeParameters | SymbolDisplayGenericsOptions.IncludeVariance,
        memberOptions: SymbolDisplayMemberOptions.IncludeParameters | SymbolDisplayMemberOptions.IncludeContainingType,
        parameterOptions: SymbolDisplayParameterOptions.IncludeType | SymbolDisplayParameterOptions.IncludeParamsRefOut | SymbolDisplayParameterOptions.IncludeName,
        miscellaneousOptions: SymbolDisplayMiscellaneousOptions.EscapeKeywordIdentifiers | SymbolDisplayMiscellaneousOptions.UseSpecialTypes);

    private static readonly SymbolDisplayFormat DisplayFormat = new(
        globalNamespaceStyle: SymbolDisplayGlobalNamespaceStyle.Omitted,
        typeQualificationStyle: SymbolDisplayTypeQualificationStyle.NameAndContainingTypes,
        genericsOptions: SymbolDisplayGenericsOptions.IncludeTypeParameters,
        memberOptions: SymbolDisplayMemberOptions.IncludeParameters | SymbolDisplayMemberOptions.IncludeContainingType,
        parameterOptions: SymbolDisplayParameterOptions.IncludeType | SymbolDisplayParameterOptions.IncludeName,
        miscellaneousOptions: SymbolDisplayMiscellaneousOptions.EscapeKeywordIdentifiers | SymbolDisplayMiscellaneousOptions.UseSpecialTypes);

    public static string? MapKind(ISymbol symbol)
    {
        return symbol switch
        {
            INamespaceSymbol ns when !ns.IsGlobalNamespace => "namespace",
            INamedTypeSymbol { IsRecord: true, TypeKind: TypeKind.Class } => "record",
            INamedTypeSymbol { IsRecord: true, TypeKind: TypeKind.Struct } => "record-struct",
            INamedTypeSymbol named => named.TypeKind switch
            {
                TypeKind.Class => "class",
                TypeKind.Struct => "struct",
                TypeKind.Interface => "interface",
                TypeKind.Enum => "enum",
                TypeKind.Delegate => "delegate",
                _ => null,
            },
            IMethodSymbol method => method.MethodKind switch
            {
                MethodKind.Ordinary => "method",
                MethodKind.Constructor => "constructor",
                MethodKind.StaticConstructor => "static-constructor",
                MethodKind.Destructor => "destructor",
                MethodKind.Conversion => "conversion-operator",
                MethodKind.UserDefinedOperator => "operator",
                _ => null,
            },
            IPropertySymbol property => property.IsIndexer ? "indexer" : "property",
            IEventSymbol => "event",
            IFieldSymbol field => field.ContainingType?.TypeKind == TypeKind.Enum
                ? "enum-member"
                : field.IsConst ? "const" : "field",
            _ => null,
        };
    }

    public static SymbolDto ToDto(ISymbol symbol, FileLinePositionSpan span)
    {
        var start = span.StartLinePosition;
        var end = span.EndLinePosition;

        var ns = symbol.ContainingNamespace is { IsGlobalNamespace: false } containingNamespace
            ? containingNamespace.ToDisplayString()
            : null;

        var qualified = symbol.ToDisplayString(QualifiedFormat);
        var display = symbol.ToDisplayString(DisplayFormat);
        var signature = symbol.ToDisplayString(QualifiedFormat);

        return new SymbolDto
        {
            Name = !string.IsNullOrEmpty(symbol.Name) ? symbol.Name : qualified,
            Identifier = symbol.Name,
            Namespace = ns,
            NamespaceName = ns,
            QualifiedName = qualified,
            DisplayName = display,
            Signature = signature,
            DisplaySignature = signature,
            StartLine = start.Line + 1,
            EndLine = end.Line + 1,
            StartColumn = start.Character + 1,
            EndColumn = end.Character + 1,
        };
    }
}

internal sealed class SymbolDto
{
    public string? Type { get; set; }
    public string? Kind { get; set; }
    public string? Name { get; set; }
    public string? Identifier { get; set; }
    public string? DisplayName { get; set; }
    public string? Signature { get; set; }
    public string? DisplaySignature { get; set; }
    public string? QualifiedName { get; set; }
    public string? Namespace { get; set; }
    public string? NamespaceName { get; set; }
    public int StartLine { get; set; }
    public int EndLine { get; set; }
    public int? StartColumn { get; set; }
    public int? EndColumn { get; set; }
}


