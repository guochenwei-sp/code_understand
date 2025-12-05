"""
Git集成辅助模块
提供Git历史、diff、blame等功能
"""
import os
import subprocess
import json
from datetime import datetime
from typing import List, Dict, Optional

class GitHelper:
    """Git操作辅助类"""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._check_git_repo()

    def _check_git_repo(self):
        """检查是否是有效的 Git 仓库"""
        git_dir = os.path.join(self.repo_path, '.git')
        if not os.path.exists(git_dir):
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git_command(self, args: List[str]) -> str:
        """执行 Git 命令"""
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace'
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Git command failed: {e}")
            return ""

    def get_commits(self, max_count: int = 50, file_path: Optional[str] = None) -> List[Dict]:
        """
        获取提交历史
        """
        args = [
            'log',
            f'--max-count={max_count}',
            '--pretty=format:%H|%an|%ae|%at|%s',
            '--'
        ]
        if file_path:
            args.append(file_path)

        output = self._run_git_command(args)
        if not output:
            return []

        commits = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 4)
            if len(parts) == 5:
                commit_hash, author_name, author_email, timestamp, message = parts
                commits.append({
                    'hash': commit_hash,
                    'author_name': author_name,
                    'author_email': author_email,
                    'timestamp': int(timestamp),
                    'message': message,
                    'date': datetime.fromtimestamp(int(timestamp)).isoformat()
                })

        return commits

    def get_diff(self, commit_hash: Optional[str] = None, file_path: Optional[str] = None) -> str:
        """
        获取 diff 内容
        如果不指定 commit_hash，返回工作区的变更
        """
        if commit_hash:
            args = ['diff', f'{commit_hash}^', commit_hash]
        else:
            args = ['diff', 'HEAD']

        if file_path:
            args.extend(['--', file_path])

        return self._run_git_command(args)

    def get_blame(self, file_path: str) -> List[Dict]:
        """
        获取文件的 blame 信息（每行的最后修改者）
        """
        args = ['blame', '--line-porcelain', file_path]
        output = self._run_git_command(args)

        if not output:
            return []

        blame_info = []
        current_commit = {}
        line_number = 0

        for line in output.split('\n'):
            if not line:
                continue

            if line[0:40].replace(' ', '').isalnum() and len(line) > 40:
                # 新的 commit 行
                parts = line.split()
                current_commit = {
                    'hash': parts[0],
                    'original_line': int(parts[1]),
                    'final_line': int(parts[2])
                }
                line_number = int(parts[2])
            elif line.startswith('author '):
                current_commit['author'] = line[7:]
            elif line.startswith('author-mail'):
                current_commit['author_email'] = line[12:].strip('<>')
            elif line.startswith('author-time'):
                current_commit['timestamp'] = int(line[12:])
            elif line.startswith('summary'):
                current_commit['summary'] = line[8:]
            elif line.startswith('\t'):
                # 实际代码行
                blame_info.append({
                    'line': line_number,
                    'content': line[1:],  # 去掉开头的 \t
                    **current_commit
                })

        return blame_info

    def get_changed_files(self, commit_hash: Optional[str] = None) -> List[Dict]:
        """
        获取变更的文件列表
        """
        if commit_hash:
            args = ['diff-tree', '--no-commit-id', '--name-status', '-r', commit_hash]
        else:
            args = ['diff', '--name-status']

        output = self._run_git_command(args)
        if not output:
            return []

        changed_files = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t', 1)
            if len(parts) == 2:
                status, path = parts
                changed_files.append({
                    'status': status,  # A=added, M=modified, D=deleted
                    'path': path
                })

        return changed_files

    def get_file_history_stats(self, file_path: str) -> Dict:
        """
        获取文件的修改统计（修改次数、贡献者等）
        """
        # 获取文件的提交次数
        commits_output = self._run_git_command(['log', '--oneline', '--', file_path])
        commit_count = len([l for l in commits_output.split('\n') if l.strip()])

        # 获取贡献者
        authors_output = self._run_git_command(['log', '--format=%an', '--', file_path])
        authors = list(set([a for a in authors_output.split('\n') if a.strip()]))

        # 最后修改时间
        last_commit_output = self._run_git_command(['log', '-1', '--format=%at', '--', file_path])
        last_modified = int(last_commit_output.strip()) if last_commit_output.strip() else 0

        return {
            'commit_count': commit_count,
            'authors': authors,
            'author_count': len(authors),
            'last_modified': last_modified
        }

    def get_commit_details(self, commit_hash: str) -> Optional[Dict]:
        """
        获取详细的提交信息
        """
        output = self._run_git_command([
            'show',
            '--pretty=format:%H|%an|%ae|%at|%s|%b',
            '--stat',
            commit_hash
        ])

        if not output:
            return None

        lines = output.split('\n')
        if not lines:
            return None

        # 第一行是提交信息
        parts = lines[0].split('|', 5)
        if len(parts) < 5:
            return None

        commit_hash, author_name, author_email, timestamp, subject = parts[0:5]
        body = parts[5] if len(parts) > 5 else ""

        # 解析统计信息
        changed_files = []
        insertions = 0
        deletions = 0

        for line in lines[1:]:
            if '|' in line and ('+' in line or '-' in line):
                # 文件统计行
                parts = line.split('|')
                if len(parts) == 2:
                    file_path = parts[0].strip()
                    stats = parts[1].strip()
                    changed_files.append({'path': file_path, 'stats': stats})
            elif 'insertion' in line or 'deletion' in line:
                # 总计行
                import re
                ins_match = re.search(r'(\d+) insertion', line)
                del_match = re.search(r'(\d+) deletion', line)
                if ins_match:
                    insertions = int(ins_match.group(1))
                if del_match:
                    deletions = int(del_match.group(1))

        return {
            'hash': commit_hash,
            'author_name': author_name,
            'author_email': author_email,
            'timestamp': int(timestamp),
            'subject': subject,
            'body': body,
            'changed_files': changed_files,
            'insertions': insertions,
            'deletions': deletions
        }

    def is_git_repo(self) -> bool:
        """检查是否是 Git 仓库"""
        try:
            self._check_git_repo()
            return True
        except:
            return False
