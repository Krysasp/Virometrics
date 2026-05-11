"""Tiered storage management for Virometrics platform.

Implements hot/warm/cold storage classification based on access patterns
and data age.
"""

import os
import sqlite3
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StorageTier(Enum):
    """Storage tier classifications."""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


# Default configuration
HOT_TIER_MAX_AGE_DAYS = 7
WARM_TIER_MAX_AGE_DAYS = 30
HOT_TIER_MAX_SIZE_GB = 10
WARM_TIER_MAX_SIZE_GB = 100


class TieredStorage:
    """Manage data across hot, warm, and cold storage tiers."""

    def __init__(self, base_dir: Optional[str] = None,
                 db_path: Optional[str] = None):
        self.base_dir = Path(base_dir or "/home/ihcm-ubuntu/Virometrics/data")
        self.db_path = db_path or str(self.base_dir.parent / 'data' / 'virometrics.db')
        
        # Storage paths
        self.hot_dir = self.base_dir / 'hot'
        self.warm_dir = self.base_dir / 'warm'
        self.cold_dir = self.base_dir / 'cold'
        
        # Create directories if they don't exist
        for tier_dir in [self.hot_dir, self.warm_dir, self.cold_dir]:
            tier_dir.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def classify_file(self, filepath: str) -> StorageTier:
        """
        Classify a file into appropriate storage tier.
        Classification based on:
        - File age (last modified time)
        - Access frequency (if tracked in database)
        - File size
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        stat = os.stat(filepath)
        file_age_days = (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
        
        # Hot: Recently modified (within 7 days) or frequently accessed
        if file_age_days <= HOT_TIER_MAX_AGE_DAYS:
            return StorageTier.HOT
        
        # Warm: Moderately recent (within 30 days)
        if file_age_days <= WARM_TIER_MAX_AGE_DAYS:
            return StorageTier.WARM
        
        # Cold: Older files
        return StorageTier.COLD

    def get_file_tier(self, filepath: str) -> StorageTier:
        """Get current tier of a file based on its location."""
        abs_path = os.path.abspath(filepath)
        
        if str(self.hot_dir) in abs_path:
            return StorageTier.HOT
        elif str(self.warm_dir) in abs_path:
            return StorageTier.WARM
        elif str(self.cold_dir) in abs_path:
            return StorageTier.COLD
        else:
            # File not in tiered storage - classify it
            return self.classify_file(filepath)

    def promote_file(self, filepath: str, target_tier: StorageTier) -> str:
        """
        Move file to a different tier.
        Returns new filepath.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        current_tier = self.get_file_tier(filepath)
        if current_tier == target_tier:
            return filepath
        
        # Determine target directory
        if target_tier == StorageTier.HOT:
            target_dir = self.hot_dir
        elif target_tier == StorageTier.WARM:
            target_dir = self.warm_dir
        else:
            target_dir = self.cold_dir
        
        # Create subdirectory structure preserving relative path
        filepath_path = Path(filepath)
        relative_path = filepath_path.relative_to(self.base_dir)
        target_path = target_dir / relative_path
        
        # Create parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move file
        shutil.move(filepath, str(target_path))
        
        # Update database if exists
        self._update_file_tier_in_db(filepath, str(target_path))
        
        logger.info(f"Promoted {filepath} to {target_tier.value} tier")
        return str(target_path)

    def demote_file(self, filepath: str) -> str:
        """
        Automatically demote file based on classification.
        Returns new filepath.
        """
        classification = self.classify_file(filepath)
        current_tier = self.get_file_tier(filepath)
        
        # Can only demote if file is in warmer tier
        tier_order = [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD]
        if tier_order.index(classification) <= tier_order.index(current_tier):
            return self.promote_file(filepath, classification)
        
        return filepath

    def _update_file_tier_in_db(self, old_path: str, new_path: str):
        """Update file tier in database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE data_files SET filepath=? WHERE filepath=?""",
                (new_path, old_path)
            )
            conn.commit()
        finally:
            conn.close()

    def get_tier_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all storage tiers."""
        stats = {}
        
        for tier in StorageTier:
            tier_dir = self._get_tier_directory(tier)
            stats[tier.value] = self._calculate_tier_stats(tier, tier_dir)
        
        return stats

    def _get_tier_directory(self, tier: StorageTier) -> Path:
        """Get directory for a storage tier."""
        if tier == StorageTier.HOT:
            return self.hot_dir
        elif tier == StorageTier.WARM:
            return self.warm_dir
        else:
            return self.cold_dir

    def _calculate_tier_stats(self, tier: StorageTier, tier_dir: Path) -> Dict[str, Any]:
        """Calculate statistics for a storage tier."""
        total_size = 0
        file_count = 0
        file_types = {}
        
        if tier_dir.exists():
            for root, dirs, files in os.walk(tier_dir):
                for f in files:
                    filepath = os.path.join(root, f)
                    try:
                        size = os.path.getsize(filepath)
                        total_size += size
                        file_count += 1
                        
                        # Track file types
                        ext = os.path.splitext(f)[1].lower() or 'no_ext'
                        file_types[ext] = file_types.get(ext, 0) + 1
                    except:
                        pass
        
        return {
            'tier': tier.value,
            'directory': str(tier_dir),
            'total_size': total_size,
            'total_size_gb': round(total_size / (1024**3), 2),
            'file_count': file_count,
            'file_types': file_types,
            'avg_file_size': round(total_size / file_count, 2) if file_count > 0 else 0
        }

    def get_tier_recommendations(self) -> List[Dict[str, Any]]:
        """
        Get recommendations for files that should be moved between tiers.
        """
        recommendations = []
        
        # Check HOT tier for files that should be moved to WARM
        for root, dirs, files in os.walk(self.hot_dir):
            for f in files:
                filepath = os.path.join(root, f)
                if self.classify_file(filepath) == StorageTier.WARM:
                    recommendations.append({
                        'current_path': filepath,
                        'current_tier': StorageTier.HOT.value,
                        'recommended_tier': StorageTier.WARM.value,
                        'reason': 'File age exceeds hot tier threshold'
                    })
        
        # Check WARM tier for files that should be moved to COLD
        for root, dirs, files in os.walk(self.warm_dir):
            for f in files:
                filepath = os.path.join(root, f)
                if self.classify_file(filepath) == StorageTier.COLD:
                    recommendations.append({
                        'current_path': filepath,
                        'current_tier': StorageTier.WARM.value,
                        'recommended_tier': StorageTier.COLD.value,
                        'reason': 'File age exceeds warm tier threshold'
                    })
        
        return recommendations

    def apply_tiering(self, dry_run: bool = False) -> Dict[str, int]:
        """
        Apply tiering recommendations to move files between tiers.
        Returns count of files moved per tier transition.
        """
        moves = {
            'hot_to_warm': 0,
            'warm_to_cold': 0,
            'hot_to_cold': 0,
            'errors': 0
        }
        
        recommendations = self.get_tier_recommendations()
        
        for rec in recommendations:
            try:
                if rec['recommended_tier'] == StorageTier.WARM.value:
                    self.promote_file(rec['current_path'], StorageTier.WARM)
                    moves['hot_to_warm'] += 1
                elif rec['recommended_tier'] == StorageTier.COLD.value:
                    self.promote_file(rec['current_path'], StorageTier.COLD)
                    moves['warm_to_cold'] += 1
            except Exception as e:
                logger.error(f"Error moving {rec['current_path']}: {e}")
                moves['errors'] += 1
        
        return moves

    def get_hot_storage_paths(self) -> List[str]:
        """Get list of paths in hot storage."""
        paths = []
        if self.hot_dir.exists():
            for root, dirs, files in os.walk(self.hot_dir):
                for f in files:
                    paths.append(os.path.join(root, f))
        return paths

    def get_warm_storage_paths(self) -> List[str]:
        """Get list of paths in warm storage."""
        paths = []
        if self.warm_dir.exists():
            for root, dirs, files in os.walk(self.warm_dir):
                for f in files:
                    paths.append(os.path.join(root, f))
        return paths

    def get_cold_storage_paths(self) -> List[str]:
        """Get list of paths in cold storage."""
        paths = []
        if self.cold_dir.exists():
            for root, dirs, files in os.walk(self.cold_dir):
                for f in files:
                    paths.append(os.path.join(root, f))
        return paths

    def ensure_file_in_correct_tier(self, filepath: str) -> Tuple[str, StorageTier]:
        """
        Ensure a file is in its correct tier based on classification.
        Returns (new_filepath, tier).
        """
        current_tier = self.get_file_tier(filepath)
        classified_tier = self.classify_file(filepath)
        
        if current_tier != classified_tier:
            new_path = self.promote_file(filepath, classified_tier)
            return new_path, classified_tier
        
        return filepath, current_tier


def main():
    """Demo tiered storage functionality."""
    storage = TieredStorage()
    
    print("Tiered Storage Statistics:")
    print("=" * 50)
    
    stats = storage.get_tier_stats()
    for tier_name, tier_stats in stats.items():
        print(f"\n{tier_name.upper()} Tier:")
        print(f"  Directory: {tier_stats['directory']}")
        print(f"  Total Size: {tier_stats['total_size_gb']} GB")
        print(f"  File Count: {tier_stats['file_count']}")
    
    print("\n" + "=" * 50)
    print("Tiering Recommendations:")
    recommendations = storage.get_tier_recommendations()
    if recommendations:
        for rec in recommendations[:5]:
            print(f"  {rec['current_path']} -> {rec['recommended_tier']}")
    else:
        print("  No recommendations")


if __name__ == '__main__':
    main()
