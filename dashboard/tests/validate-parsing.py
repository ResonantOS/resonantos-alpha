#!/usr/bin/env python3
"""
Validate the parsing functions for TODO, IDEAS, and Intelligence data.
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path

# Import parsing functions from server
sys.path.insert(0, str(Path.home() / 'clawd' / 'projects' / 'resonantos' / 'dashboard'))
from server import parse_todo_md, parse_ideas_md, parse_intelligence_md

CLAWD_DIR = Path.home() / 'clawd'

def test_todo_parsing():
    """Test TODO.md parsing"""
    print("\n=== Testing TODO Parsing ===")
    todo_file = CLAWD_DIR / 'TODO.md'
    
    if not todo_file.exists():
        print("❌ TODO.md not found")
        return False
    
    content = todo_file.read_text()
    tasks = parse_todo_md(content)
    
    print(f"✓ Parsed {len(tasks)} tasks")
    
    # Check for expected structure
    if tasks:
        task = tasks[0]
        required_keys = ['title', 'completed', 'section', 'priority', 'date']
        for key in required_keys:
            if key not in task:
                print(f"❌ Missing key in task: {key}")
                return False
            print(f"  ✓ Task has '{key}' field")
    
    # Check for different sections
    sections = set(t['section'] for t in tasks)
    print(f"✓ Found {len(sections)} sections: {sections}")
    
    # Sample task
    if tasks:
        print(f"✓ Sample task: '{tasks[0]['title']}' (completed: {tasks[0]['completed']})")
    
    return True


def test_ideas_parsing():
    """Test IDEAS.md parsing"""
    print("\n=== Testing IDEAS Parsing ===")
    ideas_file = CLAWD_DIR / 'IDEAS.md'
    
    if not ideas_file.exists():
        print("❌ IDEAS.md not found")
        return False
    
    content = ideas_file.read_text()
    ideas = parse_ideas_md(content)
    
    print(f"✓ Parsed {len(ideas)} ideas")
    
    # Check for expected structure
    if ideas:
        idea = ideas[0]
        required_keys = ['title', 'description', 'priority', 'status']
        for key in required_keys:
            if key not in idea:
                print(f"❌ Missing key in idea: {key}")
                return False
            print(f"  ✓ Idea has '{key}' field")
    
    # Check for different priorities
    priorities = set(i['priority'] for i in ideas if i['priority'])
    print(f"✓ Found {len(priorities)} priority levels: {priorities}")
    
    # Sample idea
    if ideas:
        idea = ideas[0]
        desc_preview = idea['description'][:100] + "..." if len(idea['description']) > 100 else idea['description']
        print(f"✓ Sample idea: '{idea['title']}' ({idea['priority']})")
        print(f"  Description: {desc_preview}")
    
    return True


def test_intelligence_parsing():
    """Test Intelligence parsing"""
    print("\n=== Testing Intelligence Parsing ===")
    
    # Find the most recent intelligence file
    memory_dir = CLAWD_DIR / 'memory'
    intel_files = sorted(memory_dir.glob('*community-intelligence*.md'), reverse=True)
    
    if not intel_files:
        print("❌ No community intelligence files found")
        return False
    
    intel_file = intel_files[0]
    print(f"✓ Found intelligence file: {intel_file.name}")
    
    content = intel_file.read_text()
    intelligence = parse_intelligence_md(content)
    
    # Check for expected structure
    required_keys = ['summary', 'scanDate', 'releases', 'competitors', 'opportunities']
    for key in required_keys:
        if key not in intelligence:
            print(f"❌ Missing key in intelligence: {key}")
            return False
        if isinstance(intelligence[key], list):
            print(f"  ✓ Intel has '{key}': {len(intelligence[key])} items")
        else:
            print(f"  ✓ Intel has '{key}': {intelligence[key]}")
    
    # Check contents
    print(f"\n✓ Parsed Intelligence Summary:")
    print(f"  - Releases: {len(intelligence.get('releases', []))} items")
    print(f"  - Competitors: {len(intelligence.get('competitors', []))} items")
    print(f"  - Opportunities: {len(intelligence.get('opportunities', []))} items")
    print(f"  - Scan Date: {intelligence.get('scanDate', 'Unknown')}")
    
    # Sample data
    if intelligence.get('releases'):
        rel = intelligence['releases'][0]
        print(f"\n✓ Sample Release: '{rel.get('title', 'Unknown')}' ")
        if rel.get('description'):
            desc = rel['description'][:80] + "..." if len(rel['description']) > 80 else rel['description']
            print(f"  Description: {desc}")
    
    return True


def test_data_quality():
    """Test overall data quality"""
    print("\n=== Testing Data Quality ===")
    
    # Test TODO task counts by section
    todo_file = CLAWD_DIR / 'TODO.md'
    content = todo_file.read_text()
    tasks = parse_todo_md(content)
    
    section_counts = {}
    for task in tasks:
        section = task.get('section', 'unknown')
        section_counts[section] = section_counts.get(section, 0) + 1
    
    print(f"✓ Task distribution by section:")
    for section, count in sorted(section_counts.items()):
        print(f"  - {section}: {count} tasks")
    
    # Check for priorities in tasks
    priority_counts = {}
    for task in tasks:
        priority = task.get('priority') or 'None'
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
    
    print(f"\n✓ Task distribution by priority:")
    for priority, count in sorted(priority_counts.items()):
        print(f"  - {priority}: {count} tasks")
    
    return True


def main():
    """Run all tests"""
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║  Dashboard Improvements - Parsing Validation Tests             ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    
    results = []
    
    results.append(("TODO Parsing", test_todo_parsing()))
    results.append(("IDEAS Parsing", test_ideas_parsing()))
    results.append(("Intelligence Parsing", test_intelligence_parsing()))
    results.append(("Data Quality", test_data_quality()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All validation tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
