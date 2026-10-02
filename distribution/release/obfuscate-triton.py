#!/usr/bin/env python3
"""Emit a semantically equivalent but intentionally non-descriptive Triton module.

The private repository keeps readable source. Release builds use this transformer
only for the two Python modules that must remain JIT source on the customer host.
"""
import argparse
import ast
from pathlib import Path


class Renamer(ast.NodeTransformer):
    def __init__(self, functions):
        self.functions = functions
        self.current = None
        self.maps = {}

    def visit_FunctionDef(self, node):
        original = node.name
        if original not in self.functions:
            return self.generic_visit(node)
        target = self.functions[original]
        mapping = {}
        ordered = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        for index, name in enumerate(ordered):
            mapping[name] = f'a{index}'
        # Deterministically rename assigned/local loop variables too.
        locals_seen = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                if child.id not in mapping and child.id not in ('tl', 'triton') and child.id not in locals_seen:
                    locals_seen.append(child.id)
        for index, name in enumerate(locals_seen):
            mapping[name] = f'v{index}'
        self.maps[original] = mapping
        node.name = target
        previous = self.current
        self.current = mapping
        node = self.generic_visit(node)
        self.current = previous
        return node

    def visit_Name(self, node):
        if self.current and node.id in self.current:
            node.id = self.current[node.id]
        return node

    def visit_arg(self, node):
        if self.current and node.arg in self.current:
            node.arg = self.current[node.arg]
        return self.generic_visit(node)

    def visit_Constant(self, node):
        # Triton's do_not_specialize names are strings and must track renamed args.
        if self.current and isinstance(node.value, str) and node.value in self.current:
            return ast.copy_location(ast.Constant(self.current[node.value]), node)
        return node


def strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    node.body.pop(0)


def transform(source, destination, functions):
    tree = ast.parse(source.read_text())
    strip_docstrings(tree)
    tree = Renamer(functions).visit(tree)
    ast.fix_missing_locations(tree)
    rendered = ast.unparse(tree) + '\n'
    # Release source should carry no descriptive private function names/comments.
    for name in functions:
        if name in rendered:
            raise RuntimeError('descriptive Triton identifier survived obfuscation: ' + name)
    destination.write_text(rendered)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--functions', required=True,
                   help='comma-separated source=release function names')
    a = p.parse_args()
    functions = dict(item.split('=', 1) for item in a.functions.split(','))
    transform(a.source, a.destination, functions)
