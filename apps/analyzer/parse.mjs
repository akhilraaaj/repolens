import { readFileSync } from "node:fs";

import ts from "typescript";

const PARSABLE = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);

const options = {
  noLib: true,
  allowJs: true,
  checkJs: false,
  noEmit: true,
  target: ts.ScriptTarget.Latest,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
  moduleDetection: ts.ModuleDetectionKind.Force,
  jsx: ts.JsxEmit.Preserve,
  allowImportingTsExtensions: true,
};

const input = JSON.parse(readFileSync(0, "utf8"));
applyPathAliases(input.config);
const files = new Map();
for (const file of input.files ?? []) {
  if (typeof file.path !== "string" || typeof file.content !== "string") {
    continue;
  }
  if (file.path.endsWith(".d.ts") || !PARSABLE.has(extension(file.path))) {
    continue;
  }
  files.set(internalPath(file.path), file.content);
}

const host = createHost(files);
const program = ts.createProgram([...files.keys()], options, host);
const checker = program.getTypeChecker();
const symbols = [];
const relationships = [];
const fileResults = [];
const symbolIds = new Set();

for (const [internal, content] of files) {
  const source = program.getSourceFile(internal);
  const path = externalPath(internal);
  const syntaxError = source === undefined ? "The file could not be parsed." : firstSyntaxError(source);
  if (syntaxError !== null) {
    fileResults.push({ path, parse_status: "failed", parse_error: syntaxError });
    continue;
  }
  fileResults.push({ path, parse_status: "parsed", parse_error: null });
  const moduleId = localId(path, "module", 1);
  addSymbol({
    local_id: moduleId,
    path,
    entity_type: "module",
    name: path.split("/").at(-1) ?? path,
    qualified_name: `${path}#module`,
    start_line: 1,
    end_line: lineOf(source, source.end),
    exported: false,
  });
  collectSymbols(source, path);
}
for (const internal of files.keys()) {
  const source = program.getSourceFile(internal);
  const path = externalPath(internal);
  if (source === undefined || firstSyntaxError(source) !== null) {
    continue;
  }
  collectRelationships(source, path, localId(path, "module", 1));
}

process.stdout.write(
  JSON.stringify({
    parser_name: "typescript",
    parser_version: ts.version,
    files: fileResults,
    symbols,
    relationships,
  }),
);

function createHost(sourceFiles) {
  return {
    getSourceFile(fileName, languageVersion) {
      const content = sourceFiles.get(internalPath(fileName));
      if (content === undefined) {
        return undefined;
      }
      return ts.createSourceFile(internalPath(fileName), content, languageVersion, true, scriptKind(fileName));
    },
    getDefaultLibFileName: () => "lib.d.ts",
    writeFile() {},
    getCurrentDirectory: () => "/",
    getCanonicalFileName: (fileName) => internalPath(fileName),
    useCaseSensitiveFileNames: () => true,
    getNewLine: () => "\n",
    fileExists: (fileName) => sourceFiles.has(internalPath(fileName)),
    readFile: (fileName) => sourceFiles.get(internalPath(fileName)),
    directoryExists(directoryName) {
      const prefix = internalPath(directoryName).replace(/\/$/, "");
      for (const name of sourceFiles.keys()) {
        if (name === prefix || name.startsWith(`${prefix}/`)) {
          return true;
        }
      }
      return false;
    },
    getDirectories: () => [],
  };
}

function collectSymbols(source, path) {
  visit(source);
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name) {
      recordDeclaration(path, node, node.name.text, "function", null);
    } else if (ts.isClassDeclaration(node) && node.name) {
      recordDeclaration(path, node, node.name.text, "class", null);
    } else if (ts.isMethodDeclaration(node) && ts.isIdentifier(node.name)) {
      const owner = ts.isClassDeclaration(node.parent) && node.parent.name ? node.parent.name.text : null;
      recordDeclaration(path, node, node.name.text, "method", owner);
    } else if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
      const callable = node.initializer !== undefined && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer));
      const exported = isExported(node);
      if (callable || exported) {
        recordDeclaration(path, node, node.name.text, callable ? "function" : "value", null);
      }
    }
    ts.forEachChild(node, visit);
  }
}

function collectRelationships(source, path, moduleId) {
  visit(source);
  function visit(node) {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      recordModuleEdge(source, path, moduleId, node.moduleSpecifier, "imports");
    } else if (ts.isExportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      recordModuleEdge(source, path, moduleId, node.moduleSpecifier, "exports");
    } else if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || isRequire(node))) {
      const argument = node.arguments[0];
      if (argument && ts.isStringLiteral(argument)) {
        recordModuleEdge(source, path, moduleId, argument, "imports");
      } else if (argument) {
        relationships.push(edge(source, moduleId, null, "imports", "unresolved", argument.getText(source), null, argument));
      }
    } else if ((ts.isCallExpression(node) || ts.isNewExpression(node)) && node.expression && ts.isIdentifier(node.expression)) {
      recordCall(source, path, moduleId, node, node.expression, "calls");
    } else if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
      recordCall(source, path, moduleId, node, node.expression.name, "calls");
    } else if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && isComponentTag(node.tagName)) {
      recordCall(source, path, moduleId, node, node.tagName, "renders");
    }
    ts.forEachChild(node, visit);
  }
}

function isRequire(node) {
  return ts.isIdentifier(node.expression) && node.expression.text === "require" && node.arguments.length === 1;
}

function isComponentTag(tagName) {
  return ts.isIdentifier(tagName) && /^[A-Z]/.test(tagName.text);
}

/**
 * Copy baseUrl and paths from the root tsconfig.json or jsconfig.json.
 * The file is parsed as JSON text. "extends" and plugins are ignored.
 */
function applyPathAliases(config) {
  if (!config || typeof config.content !== "string") {
    return;
  }
  const parsed = ts.parseConfigFileTextToJson(config.path ?? "tsconfig.json", config.content);
  const compilerOptions = parsed.config?.compilerOptions;
  if (!compilerOptions || typeof compilerOptions !== "object") {
    return;
  }
  const directory = typeof config.path === "string" && config.path.includes("/") ? config.path.slice(0, config.path.lastIndexOf("/")) : "";
  const base = typeof compilerOptions.baseUrl === "string" ? joinPath(directory, compilerOptions.baseUrl) : directory;
  if (typeof compilerOptions.baseUrl === "string" || isPathMap(compilerOptions.paths)) {
    options.baseUrl = internalPath(base || ".");
  }
  if (isPathMap(compilerOptions.paths)) {
    options.paths = compilerOptions.paths;
  }
}

function isPathMap(value) {
  return (
    typeof value === "object" &&
    value !== null &&
    Object.values(value).every((targets) => Array.isArray(targets) && targets.every((target) => typeof target === "string"))
  );
}

function joinPath(directory, relative) {
  const parts = [];
  for (const part of `${directory}/${relative}`.split("/")) {
    if (part === "" || part === ".") {
      continue;
    }
    if (part === "..") {
      parts.pop();
    } else {
      parts.push(part);
    }
  }
  return parts.join("/");
}

function recordModuleEdge(source, path, moduleId, specifierNode, relationshipType) {
  const specifier = specifierNode.text;
  const resolved = ts.resolveModuleName(specifier, source.fileName, options, host).resolvedModule;
  const targetPath = resolved ? externalPath(resolved.resolvedFileName) : null;
  const targetId = targetPath && files.has(internalPath(targetPath)) ? localId(targetPath, "module", 1) : null;
  const status = targetId === null ? "unresolved" : specifier.startsWith(".") ? "verified" : "resolved";
  relationships.push(edge(source, moduleId, targetId, relationshipType, status, specifier, null, specifierNode));
}

function recordCall(source, path, moduleId, node, nameNode, relationshipType) {
  const called = checker.getSymbolAtLocation(nameNode);
  const target = called && (called.flags & ts.SymbolFlags.Alias) !== 0 ? checker.getAliasedSymbol(called) : called;
  const declaration = target?.declarations?.find((item) => symbolIds.has(idForNode(item)));
  if (!declaration) {
    return;
  }
  const sourceId = enclosingSymbolId(node, path, moduleId);
  relationships.push(edge(source, sourceId, idForNode(declaration), relationshipType, "resolved", null, nameNode.text, nameNode));
}

function recordDeclaration(path, node, name, entityType, owner) {
  const start = lineOf(node.getSourceFile(), node.getStart(node.getSourceFile()));
  const id = localId(path, owner ? `${owner}.${name}` : name, start);
  addSymbol({
    local_id: id,
    path,
    entity_type: entityType,
    name,
    qualified_name: `${path}#${owner ? `${owner}.${name}` : name}`,
    start_line: start,
    end_line: lineOf(node.getSourceFile(), node.end),
    exported: isExported(node),
  });
}

function addSymbol(symbol) {
  if (symbolIds.has(symbol.local_id)) {
    return;
  }
  symbolIds.add(symbol.local_id);
  symbols.push(symbol);
}

function idForNode(node) {
  const source = node.getSourceFile();
  const path = externalPath(source.fileName);
  const start = lineOf(source, node.getStart(source));
  if (ts.isFunctionDeclaration(node) && node.name) {
    return localId(path, node.name.text, start);
  }
  if (ts.isClassDeclaration(node) && node.name) {
    return localId(path, node.name.text, start);
  }
  if (ts.isMethodDeclaration(node) && ts.isIdentifier(node.name)) {
    const owner = ts.isClassDeclaration(node.parent) && node.parent.name ? node.parent.name.text : null;
    return localId(path, owner ? `${owner}.${node.name.text}` : node.name.text, start);
  }
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
    return localId(path, node.name.text, start);
  }
  return null;
}

function enclosingSymbolId(node, path, moduleId) {
  let current = node.parent;
  while (current) {
    const id = idForNode(current);
    if (id && symbolIds.has(id)) {
      return id;
    }
    current = current.parent;
  }
  return moduleId;
}

function edge(source, sourceId, targetId, relationshipType, resolutionStatus, specifier, targetName, evidenceNode) {
  return {
    relationship_type: relationshipType,
    resolution_status: resolutionStatus,
    source_local_id: sourceId,
    target_local_id: targetId,
    evidence_file: externalPath(source.fileName),
    evidence_start_line: lineOf(source, evidenceNode.getStart(source)),
    evidence_end_line: lineOf(source, evidenceNode.end),
    specifier,
    target_name: targetName,
  };
}

function isExported(node) {
  const flags = ts.getCombinedModifierFlags(node);
  if ((flags & ts.ModifierFlags.Export) !== 0) {
    return true;
  }
  return node.parent ? (ts.getCombinedModifierFlags(node.parent) & ts.ModifierFlags.Export) !== 0 : false;
}

function firstSyntaxError(source) {
  const diagnostic = source.parseDiagnostics.find((item) => item.category === ts.DiagnosticCategory.Error);
  if (!diagnostic) {
    return null;
  }
  return ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n");
}

function lineOf(source, position) {
  return source.getLineAndCharacterOfPosition(position).line + 1;
}

function localId(path, name, line) {
  return `${path}#${name}@${line}`;
}

function internalPath(fileName) {
  const normalized = String(fileName).replace(/\\/g, "/").replace(/\/+/g, "/");
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
}

function externalPath(fileName) {
  return internalPath(fileName).slice(1);
}

function extension(fileName) {
  const match = fileName.match(/(\.[^./]+)$/);
  return match ? match[1] : "";
}

function scriptKind(fileName) {
  if (fileName.endsWith(".tsx")) {
    return ts.ScriptKind.TSX;
  }
  if (fileName.endsWith(".jsx")) {
    return ts.ScriptKind.JSX;
  }
  if (fileName.endsWith(".ts")) {
    return ts.ScriptKind.TS;
  }
  return ts.ScriptKind.JS;
}
