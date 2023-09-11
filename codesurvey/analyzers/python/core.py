import ast
from multiprocessing import Process, Queue
import re
from typing import Optional

import astpath
from lxml.etree import Element

from codesurvey.analyzers import FileAnalyzer, FileInfo
from codesurvey.utils import logger

SITE_PACKAGES_REGEX = re.compile(r'.*[/\\]site-packages[/\\].*')


def py_site_packages_filter(file_info):
    """Filter to exclude files under a `site-packages` directory."""
    return SITE_PACKAGES_REGEX.fullmatch(file_info.rel_path)


class PythonAstAnalyzer(FileAnalyzer[Element]):
    """Analyzer that finds .py files and parses them into lxml documents
    representing Python abstract syntax trees for feature analysis."""
    default_name = 'python'
    default_file_glob = '**/*.py'
    default_file_filters = [
        py_site_packages_filter,
    ]
    """Excludes files under a `site-packages` directory that are unlikely
    to belong to the Repo under analysis."""

    def _subprocess_parse_ast(self, *, queue: Queue, file_text: str):
        try:
            file_tree = ast.parse(file_text)
        except Exception as ex:
            queue.put(ex)
        else:
            queue.put(file_tree)

    def prepare_file(self, file_info: FileInfo) -> Optional[Element]:
        with open(file_info.abs_path, 'r') as f:
            file_text = f.read()

        # Parse ast in a subprocess, as sufficiently complex files can
        # crash the interpreter:
        # https://docs.python.org/3/library/ast.html#ast.parse
        queue: Queue = Queue()
        process = Process(target=self._subprocess_parse_ast, kwargs=dict(
            queue=queue,
            file_text=file_text,
        ))
        try:
            process.start()
            result = queue.get()
            process.join()
            if isinstance(result, Exception):
                raise result
        except (SyntaxError, ValueError) as ex:
            logger.error((f'Skipping Python file "{file_info.rel_path}" in '
                          f'repo "{file_info.repo}" that could not be parsed: {ex}'))
            return None

        file_tree = result
        file_xml = astpath.convert_to_xml(file_tree)
        return file_xml
