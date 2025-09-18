#!/usr/bin/env python
"""
NetDiscoverIT CLI: Scan, discover, identify, categorize, and document networks.
Usage: poetry run netdiscoverit --help
"""

import typer
from pathlib import Path
from typing import Optional

from netdiscoverit.core.engine import DiscoveryEngine
from netdiscoverit.core.plugins import PluginManager

app = typer.Typer(help="NetDiscoverIT: ITIL-Compliant Network Discovery Tool")

@app.command()
def scan(
    target: str = typer.Argument(..., help="Network range (e.g., 192.168.1.0/24)"),
    output_dir: Path = typer.Option(Path("results"), "--output-dir", help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging"),
):
    """Scan and discover devices on the target network."""
    engine = DiscoveryEngine()
    engine.load_plugins()  # Initialize modular plugins
    results = engine.run_discovery(target, verbose=verbose)
    
    # Basic output: Save JSON
    output_path = output_dir / "scan_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        import json
        json.dump(results, f, indent=2)
    
    typer.echo(f"Discovery complete! Results saved to {output_path}")
    typer.echo(f"Found {len(results.get('devices', []))} devices.")

@app.command()
def generate_docs(
    scan_file: Path = typer.Argument(..., help="Path to scan JSON file"),
    template: str = typer.Option("itil_cmdb", "--template", help="Doc template (e.g., itil_cmdb, incident_report)"),
):
    """Generate ITIL-compliant documentation from scan data."""
    engine = DiscoveryEngine()
    docs = engine.generate_documentation(scan_file, template)
    pdf_path = scan_file.parent / f"{scan_file.stem}_{template}.pdf"
    # Stub: Use ReportLab/Jinja2 in documenter module
    typer.echo(f"Docs generated: {pdf_path}")

if __name__ == "__main__":
    app()