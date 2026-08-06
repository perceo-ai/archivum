from __future__ import annotations

from pathlib import Path

from archivum.archgraph.extractors.base import (
    _file_stem,
    _make_id,
    _read_text,
    _source_location,
)
from archivum.archgraph.models import CodeEdge, CodeNode, Extraction, ExtractionMethod
from archivum.archgraph.registry import LanguageConfig, config_for_suffix, load_parser


def extract_file(path: Path) -> Extraction:
    """Dispatch extraction by file suffix. Returns Extraction with error on unknown suffix."""
    cfg = config_for_suffix(path.suffix)
    if cfg is None:
        return Extraction(nodes=[], edges=[], error=f"unsupported suffix {path.suffix!r}")
    return _extract_generic(path, cfg)


def _extract_generic(path: Path, cfg: LanguageConfig) -> Extraction:
    """Walk a tree-sitter parse tree and emit CodeNodes + CodeEdges."""
    try:
        source = path.read_bytes()
        parser = load_parser(cfg)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as exc:
        return Extraction(nodes=[], edges=[], error=str(exc))

    nodes: list[CodeNode] = []
    edges: list[CodeEdge] = []

    stem = _file_stem(path)
    file_id = _make_id(stem)

    # Emit the file node
    nodes.append(
        CodeNode(
            id=file_id,
            label=stem,
            kind="file",
            source_file=str(path),
            source_location=_source_location(root),
        )
    )

    # First pass: collect class names and their node spans for enclosing-class lookup
    # Build a mapping: tree-sitter node id -> class name (for class_definition nodes)
    class_node_names: dict[int, str] = {}

    def _find_classes(node) -> None:  # type: ignore[no-untyped-def]
        if node.type in cfg.class_types:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                class_node_names[node.id] = _read_text(name_node, source)
        for child in node.children:
            _find_classes(child)

    _find_classes(root)

    def _enclosing_class(node) -> str | None:
        """Walk ancestors looking for a class_definition node."""
        current = node.parent
        while current is not None:
            if current.type in cfg.class_types:
                return class_node_names.get(current.id)
            current = current.parent
        return None

    def _walk(node) -> None:  # type: ignore[no-untyped-def]
        if node.type in cfg.class_types:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _read_text(name_node, source)
                nodes.append(
                    CodeNode(
                        id=_make_id(stem, name),
                        label=name,
                        kind="type",
                        source_file=str(path),
                        source_location=_source_location(node),
                    )
                )

        elif node.type in cfg.function_types:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                fname = _read_text(name_node, source)
                enc_class = _enclosing_class(node)
                if enc_class is not None:
                    sym_id = _make_id(stem, enc_class, fname)
                else:
                    sym_id = _make_id(stem, fname)
                nodes.append(
                    CodeNode(
                        id=sym_id,
                        label=fname,
                        kind="symbol",
                        source_file=str(path),
                        source_location=_source_location(node),
                    )
                )

        elif node.type in cfg.import_types:
            _emit_import(node)

        elif node.type in cfg.call_types:
            _emit_call(node)

        for child in node.children:
            _walk(child)

    def _emit_import(node) -> None:
        """Emit an imports edge from the file node to the imported module."""
        if node.type == "import_statement":
            # import math  OR  import os, sys
            # children: "import" keyword, then name nodes
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    # dotted_name for simple imports; get first dotted_name inside aliased_import
                    actual = child
                    if child.type == "aliased_import":
                        actual = child.children[0]  # the module name part
                    module_name = _read_text(actual, source).split(".")[0]
                    target_id = _make_id(module_name)
                    edges.append(
                        CodeEdge(
                            source=file_id,
                            target=target_id,
                            relation="imports",
                            method=ExtractionMethod.EXTRACTED,
                            source_file=str(path),
                            source_location=_source_location(node),
                        )
                    )
        elif node.type == "import_from_statement":
            # from x import y  -> module is x
            mod_node = node.child_by_field_name("module_name")
            if mod_node is not None:
                module_name = _read_text(mod_node, source).split(".")[0]
                target_id = _make_id(module_name)
                edges.append(
                    CodeEdge(
                        source=file_id,
                        target=target_id,
                        relation="imports",
                        method=ExtractionMethod.EXTRACTED,
                        source_file=str(path),
                        source_location=_source_location(node),
                    )
                )

    def _enclosing_function_id(node) -> str | None:
        """Walk ancestors to find the nearest enclosing function and return its symbol id."""
        current = node.parent
        enc_class: str | None = None
        while current is not None:
            if current.type in cfg.function_types:
                fn_name_node = current.child_by_field_name("name")
                if fn_name_node is None:
                    return None
                fn_name = _read_text(fn_name_node, source)
                # find the class enclosing this function
                if enc_class is None:
                    # look further up for a class
                    cls = _enclosing_class(current)
                else:
                    cls = enc_class
                if cls is not None:
                    return _make_id(stem, cls, fn_name)
                return _make_id(stem, fn_name)
            if current.type in cfg.class_types:
                enc_class = class_node_names.get(current.id)
            current = current.parent
        return None

    def _emit_call(node) -> None:
        """Emit a calls edge from the enclosing function to the callee."""
        caller_id = _enclosing_function_id(node)
        if caller_id is None:
            return  # call not inside a function (e.g. module-level)

        fn_child = node.child_by_field_name("function")
        if fn_child is None:
            return

        if fn_child.type == "identifier":
            # bare name call: foo(...)
            callee_name = _read_text(fn_child, source)
            # best-effort: check if there's a class node with this method in same file
            enc_fn_class = _get_enclosing_class_for_function_id(caller_id)
            if enc_fn_class is not None and _make_id(stem, enc_fn_class, callee_name) in {n.id for n in nodes}:
                target_id = _make_id(stem, enc_fn_class, callee_name)
            else:
                target_id = _make_id(callee_name)

        elif fn_child.type == "attribute":
            # attribute call: obj.method(...)
            obj_node = fn_child.child_by_field_name("object")
            attr_node = fn_child.child_by_field_name("attribute")
            if obj_node is None or attr_node is None:
                return
            obj_text = _read_text(obj_node, source)
            attr_text = _read_text(attr_node, source)

            if obj_text == "self":
                # self.method -> resolve to same-class method
                enc_fn_class = _get_enclosing_class_for_function_id(caller_id)
                if enc_fn_class is not None:
                    target_id = _make_id(stem, enc_fn_class, attr_text)
                else:
                    target_id = _make_id(stem, attr_text)
            else:
                # external: obj.method -> _make_id(obj, method)
                target_id = _make_id(obj_text, attr_text)
        else:
            return

        edges.append(
            CodeEdge(
                source=caller_id,
                target=target_id,
                relation="calls",
                method=ExtractionMethod.EXTRACTED,
                source_file=str(path),
                source_location=_source_location(node),
            )
        )

    def _get_enclosing_class_for_function_id(fn_id: str) -> str | None:
        """Given a function symbol id (e.g. 'calc_calculator_hypot'), find its class.
        We do this by looking up the function node in our collected node list."""
        for n in nodes:
            if n.id == fn_id and n.kind == "symbol":
                # The class name sits between stem and fname in the id.
                # Simpler: search class_node_names values
                pass
        # Re-derive: parse fn_id pieces
        # fn_id = _make_id(stem, class_name, fn_name) or _make_id(stem, fn_name)
        # We'll search via nodes
        for n in nodes:
            if n.id == fn_id and n.kind == "symbol":
                fn_label = n.label
                # try to find a class with id = _make_id(stem, class_name)
                for cls_name in class_node_names.values():
                    candidate = _make_id(stem, cls_name, fn_label)
                    if candidate == fn_id:
                        return cls_name
        return None

    try:
        _walk(root)
    except Exception as exc:
        return Extraction(nodes=[], edges=[], error=str(exc))

    return Extraction(nodes=nodes, edges=edges)
