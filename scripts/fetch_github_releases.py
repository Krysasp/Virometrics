#!/usr/bin/env python3
"""
Fetch GitHub release information and README for all Virometrics tools.
Enhances tool metadata with release notes, latest version, README content, and repo metadata.
"""

import json
import requests
import time
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
import base64

class GitHubReleaseFetcher:
    """Fetch GitHub release information and README for tools."""
    
    def __init__(self, token: Optional[str] = None, rate_limit: int = 30):
        self.token = token
        self.base_url = "https://api.github.com"
        self.rate_limit = rate_limit  # requests per minute
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {'Accept': 'application/vnd.github.v3+json'}
        if self.token:
            headers['Authorization'] = f'token {self.token}'
        return headers
    
    def _rate_limit_sleep(self, last_request_time: float) -> float:
        """Sleep to respect rate limit."""
        elapsed = time.time() - last_request_time
        required = 60.0 / self.rate_limit
        if elapsed < required:
            time.sleep(required - elapsed)
        return time.time()
    
    def extract_repo_info(self, url: str) -> Optional[Tuple[str, str]]:
        """Extract owner and repo from GitHub URL."""
        if not url:
            return None
        
        patterns = [
            r'github\.com/([^/]+)/([^/]+?)(?:\.git)?$',
            r'github\.com/([^/]+)/([^/]+?)/?(?:tree|releases|blob)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        
        return None
    
    def fetch_release_info(self, url: str) -> Dict:
        """Fetch latest release information for a GitHub repo."""
        repo_info = self.extract_repo_info(url)
        if not repo_info:
            return {'error': 'Could not parse GitHub URL'}
        
        owner, repo = repo_info
        last_time = time.time()
        self._rate_limit_sleep(last_time)
        
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/releases/latest",
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                release = response.json()
                return {
                    'latest_version': release.get('tag_name', 'unknown'),
                    'release_name': release.get('name', release.get('tag_name')),
                    'release_date': release.get('published_at'),
                    'release_notes': release.get('body', ''),
                    'prerelease': release.get('prerelease', False),
                    'draft': release.get('draft', False),
                    'assets': [
                        {
                            'name': asset.get('name'),
                            'size': asset.get('size'),
                            'download_count': asset.get('download_count'),
                            'browser_download_url': asset.get('browser_download_url')
                        }
                        for asset in release.get('assets', [])
                    ],
                    'asset_count': release.get('asset_count', 0),
                }
            elif response.status_code == 404:
                return {'no_releases': True, 'message': 'No releases found'}
            else:
                return {'error': f'API returned {response.status_code}'}
                
        except requests.exceptions.Timeout:
            return {'error': 'Request timed out'}
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}
        finally:
            self._rate_limit_sleep(time.time())
    
    def fetch_readme(self, url: str) -> Dict:
        """Fetch README.md content for a GitHub repo."""
        repo_info = self.extract_repo_info(url)
        if not repo_info:
            return {'error': 'Could not parse GitHub URL'}
        
        owner, repo = repo_info
        last_time = time.time()
        self._rate_limit_sleep(last_time)
        
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/readme",
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                content = base64.b64decode(response.json().get('content', '')).decode('utf-8')
                sections = self._parse_readme_sections(content)
                
                return {
                    'raw_content': content,
                    'length': len(content),
                    'sections': sections,
                    'has_install_section': 'INSTALL' in str(sections.get('headers', [])),
                    'has_usage_section': 'USAGE' in str(sections.get('headers', [])),
                    'has_requirements_section': 'REQUIREMENTS' in str(sections.get('headers', [])),
                    'has_development_section': 'DEVELOPMENT' in str(sections.get('headers', [])),
                }
            else:
                return {'not_found': True, 'message': 'README.md not found'}
                
        except requests.exceptions.Timeout:
            return {'error': 'Request timed out'}
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}
        finally:
            self._rate_limit_sleep(time.time())
    
    def _parse_readme_sections(self, content: str) -> Dict:
        """Parse README into sections."""
        headers = re.findall(r'#+\s+([A-Z0-9\s_-]+)', content, re.IGNORECASE)
        
        sections = {}
        for header in headers:
            header_pattern = rf'#+\s+{header}\s*\n(.*?)(?=#+\s+[A-Z0-9\s_-]+|$)'
            match = re.search(header_pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                sections[header.upper()] = match.group(1).strip()[:1000]
        
        return {
            'headers': headers,
            'sections': sections
        }
    
    def fetch_repo_metadata(self, url: str) -> Dict:
        """Fetch general repository metadata."""
        repo_info = self.extract_repo_info(url)
        if not repo_info:
            return {'error': 'Could not parse GitHub URL'}
        
        owner, repo = repo_info
        last_time = time.time()
        self._rate_limit_sleep(last_time)
        
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}",
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                repo_data = response.json()
                return {
                    'full_name': repo_data.get('full_name'),
                    'description': repo_data.get('description'),
                    'homepage': repo_data.get('homepage'),
                    'language': repo_data.get('language'),
                    'size': repo_data.get('size'),
                    'stargazers_count': repo_data.get('stargazers_count'),
                    'watchers_count': repo_data.get('watchers_count'),
                    'forks_count': repo_data.get('forks_count'),
                    'open_issues_count': repo_data.get('open_issues_count'),
                    'default_branch': repo_data.get('default_branch'),
                    'archived': repo_data.get('archived'),
                    'disabled': repo_data.get('disabled'),
                    'created_at': repo_data.get('created_at'),
                    'updated_at': repo_data.get('updated_at'),
                    'pushed_at': repo_data.get('pushed_at'),
                    'has_issues': repo_data.get('has_issues'),
                    'has_projects': repo_data.get('has_projects'),
                    'has_wiki': repo_data.get('has_wiki'),
                    'has_downloads': repo_data.get('has_downloads'),
                    'license': repo_data.get('license', {}).get('name') if repo_data.get('license') else None,
                    'topics': repo_data.get('topics', []),
                    'contributor_count': self._get_contributor_count(owner, repo),
                    'release_count': self._get_release_count(owner, repo),
                }
            else:
                return {'error': f'API returned {response.status_code}'}
                
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}
        finally:
            self._rate_limit_sleep(time.time())
    
    def _get_contributor_count(self, owner: str, repo: str) -> int:
        """Get total contributor count."""
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/contributors?per_page=1",
                headers=self._get_headers(),
                timeout=5
            )
            if response.status_code == 200:
                link = response.headers.get('Link', '')
                if 'rel="last"' in link:
                    last_page = re.search(r'page=(\d+)', link.split('rel="last"')[1])
                    if last_page:
                        return int(last_page.group(1))
            return len(response.json())
        except:
            return 0
    
    def _get_release_count(self, owner: str, repo: str) -> int:
        """Get total release count."""
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/releases?per_page=1",
                headers=self._get_headers(),
                timeout=5
            )
            if response.status_code == 200:
                link = response.headers.get('Link', '')
                if 'rel="last"' in link:
                    last_page = re.search(r'page=(\d+)', link.split('rel="last"')[1])
                    if last_page:
                        return int(last_page.group(1))
            return len(response.json())
        except:
            return 0


def enhance_tool_with_github_data(tool: Dict, fetcher: GitHubReleaseFetcher) -> Dict:
    """Enhance a single tool with GitHub release and README data."""
    enhanced = tool.copy()
    
    url = tool.get('url')
    if not url or 'github.com' not in url:
        return enhanced
    
    release_info = fetcher.fetch_release_info(url)
    enhanced['github_release'] = json.dumps(release_info)
    
    readme_info = fetcher.fetch_readme(url)
    enhanced['github_readme'] = json.dumps(readme_info)
    
    repo_metadata = fetcher.fetch_repo_metadata(url)
    enhanced['github_metadata'] = json.dumps(repo_metadata)
    
    return enhanced


def create_cache_files(enhanced_tools: List[Dict], cache_dir: Path) -> int:
    """Create individual cache files for each tool."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    
    for tool in enhanced_tools:
        name = tool.get('name', 'unknown')
        cache_file = cache_dir / f"{name.replace(' ', '_')}.json"
        
        with open(cache_file, 'w') as f:
            json.dump(tool, f, indent=2)
        created += 1
    
    return created


def main():
    """Main function to enhance all tools with GitHub data."""
    start_time = time.time()
    
    # Paths
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    tools_file = data_dir / 'tools_enhanced.json'
    output_file = data_dir / 'tools_with_releases.json'
    cache_dir = data_dir / 'cache'
    
    # Load tools
    print(f"Loading tools from {tools_file}...")
    with open(tools_file, 'r') as f:
        tools = json.load(f)
    
    print(f"Loaded {len(tools)} tools")
    
    # Initialize fetcher
    token = os.environ.get('GITHUB_TOKEN')
    rate_limit = 50 if token else 30
    fetcher = GitHubReleaseFetcher(token=token, rate_limit=rate_limit)
    
    if token:
        print(f"Using authenticated API (rate limit: {rate_limit} req/min)")
    else:
        print(f"Using unauthenticated API (rate limit: {rate_limit} req/min)")
    
    # Enhance tools
    enhanced_tools = []
    errors = []
    successes = []
    no_github = []
    
    total = len(tools)
    
    for i, tool in enumerate(tools):
        url = tool.get('url')
        name = tool.get('name', 'Unknown')
        
        if url and 'github.com' in url:
            progress = (i + 1) / total * 100
            print(f"[{i+1}/{total}] ({progress:.0f}%) Enhancing {name}...")
            
            try:
                enhanced = enhance_tool_with_github_data(tool, fetcher)
                enhanced_tools.append(enhanced)
                
                # Track success/failure
                release_info = json.loads(enhanced.get('github_release', '{}'))
                if 'error' not in release_info and not release_info.get('no_releases'):
                    successes.append(name)
                else:
                    errors.append({'name': name, 'url': url, 'release_error': release_info})
                    
            except Exception as e:
                print(f"  Error enhancing {name}: {e}")
                errors.append({'name': name, 'url': url, 'error': str(e)})
                enhanced_tools.append(tool)
        else:
            no_github.append(name)
            enhanced_tools.append(tool)
    
    # Save enhanced tools
    print(f"\nSaving enhanced data to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(enhanced_tools, f, indent=2)
    
    # Create cache files
    print(f"Creating cache files in {cache_dir}...")
    cache_count = create_cache_files(enhanced_tools, cache_dir)
    
    # Calculate timing
    elapsed_time = time.time() - start_time
    
    # Print summary report
    print("\n" + "=" * 60)
    print("SUMMARY REPORT")
    print("=" * 60)
    print(f"Total tools processed: {total}")
    print(f"Tools with GitHub URLs: {len(successes) + len(errors)}")
    print(f"Tools without GitHub URLs: {len(no_github)}")
    print(f"Successfully enhanced: {len(successes)}")
    print(f"Failed enhancements: {len(errors)}")
    print(f"Cache files created: {cache_count}")
    print(f"Total time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    
    if errors:
        print(f"\nFailed tools ({len(errors)}):")
        for err in errors[:10]:  # Show first 10 errors
            print(f"  - {err['name']}: {err.get('release_error', err.get('error', 'unknown'))}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
    
    # Sample of enhanced data structure
    if enhanced_tools:
        sample = next((t for t in enhanced_tools if t.get('github_release')), None)
        if sample:
            print(f"\nSample enhanced data structure for '{sample.get('name')}':")
            print(f"  github_release keys: {list(json.loads(sample.get('github_release', '{}')).keys())}")
            print(f"  github_readme keys: {list(json.loads(sample.get('github_readme', '{}')).keys())}")
            print(f"  github_metadata keys: {list(json.loads(sample.get('github_metadata', '{}')).keys())}")
    
    print(f"\nOutput files:")
    print(f"  - {output_file}")
    print(f"  - {cache_dir}/ ({cache_count} files)")
    
    return {
        'total': total,
        'successes': len(successes),
        'failures': len(errors),
        'no_github': len(no_github),
        'cache_files': cache_count,
        'time_elapsed': elapsed_time,
        'errors': errors,
        'sample': sample
    }


if __name__ == '__main__':
    result = main()
