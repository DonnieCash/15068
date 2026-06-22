"""Command-line interface for the New Kensington digital twin.

Examples
--------
Build the bundled twin to a schematic and a preview image::

    python -m newken_twin build --out build/new_kensington.schem --preview build/preview.png

Use a custom dataset, or pull live OpenStreetMap data::

    python -m newken_twin build --dataset my_city.json
    python -m newken_twin build --osm --radius 700

Print statistics about a dataset without building::

    python -m newken_twin info
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import __version__
from .builder import CityBuilder
from .data import load_default_city
from .geo import LatLon, bbox_around
from .model import City, load_city
from .preview import write_preview
from .schematic import write_schematic


def _load_city(args) -> City:
    if args.osm:
        from .osm import OverpassError, fetch_city
        center = LatLon(args.lat, args.lon)
        box = bbox_around(center, args.radius, args.radius)
        try:
            print(f"Fetching OpenStreetMap data around {center} (r={args.radius} m)...")
            return fetch_city(box, center=center)
        except OverpassError as exc:
            print(f"  ! {exc}", file=sys.stderr)
            print("  ! Falling back to the bundled dataset.", file=sys.stderr)
            return load_default_city()
    if args.dataset:
        return load_city(args.dataset)
    return load_default_city()


def _cmd_build(args) -> int:
    city = _load_city(args)
    print(f"City: {city.name}")
    print(f"  buildings={len(city.buildings)} roads={len(city.roads)} "
          f"areas={len(city.areas)} points={len(city.points)}")

    builder = CityBuilder(city, meters_per_block=args.scale)
    proj = builder.projection
    print(f"  grid: {proj.width_blocks} x {proj.height_blocks} blocks "
          f"({proj.width_m:.0f} x {proj.height_m:.0f} m, "
          f"{args.scale} m/block)")

    t0 = time.time()
    result = builder.build()
    vol = result.volume
    print(f"  volume: {vol.width} x {vol.height} x {vol.length} "
          f"= {vol.width * vol.height * vol.length:,} cells "
          f"(built in {time.time() - t0:.1f}s)")

    _ensure_parent(args.out)
    write_schematic(args.out, vol, name=f"{city.name} - Digital Twin",
                    data_version=args.data_version)
    size = os.path.getsize(args.out)
    print(f"  wrote schematic: {args.out} ({size:,} bytes)")

    if args.preview:
        _ensure_parent(args.preview)
        write_preview(args.preview, vol, scale=args.preview_scale)
        print(f"  wrote preview:   {args.preview} "
              f"({os.path.getsize(args.preview):,} bytes)")
    return 0


def _cmd_info(args) -> int:
    city = _load_city(args)
    box = city.bounding_box()
    print(f"City: {city.name}")
    print(f"  center: {city.center.lat:.5f}, {city.center.lon:.5f}")
    print(f"  bbox:   S{box.south:.5f} W{box.west:.5f} "
          f"N{box.north:.5f} E{box.east:.5f}")
    print(f"  buildings: {len(city.buildings)}")
    print(f"  roads:     {len(city.roads)}")
    print(f"  areas:     {len(city.areas)}")
    print(f"  points:    {len(city.points)}")
    named = [p.name for p in city.points if p.kind == "landmark" and p.name]
    if named:
        print("  landmarks: " + ", ".join(named))
    return 0


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="newken_twin",
        description="Build a Minecraft digital twin of New Kensington, PA.")
    p.add_argument("--version", action="version",
                   version=f"newken_twin {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_source_args(sp):
        sp.add_argument("--dataset", help="path to a GeoJSON-style dataset")
        sp.add_argument("--osm", action="store_true",
                        help="fetch live OpenStreetMap data (needs network)")
        sp.add_argument("--lat", type=float, default=40.5695,
                        help="center latitude for --osm")
        sp.add_argument("--lon", type=float, default=-79.7647,
                        help="center longitude for --osm")
        sp.add_argument("--radius", type=float, default=650.0,
                        help="half-extent in metres for --osm")

    b = sub.add_parser("build", help="build the schematic")
    add_source_args(b)
    b.add_argument("--out", default="build/new_kensington.schem",
                   help="output .schem path")
    b.add_argument("--preview", default="build/new_kensington_preview.png",
                   help="output PNG preview path ('' to skip)")
    b.add_argument("--preview-scale", type=int, default=1,
                   help="integer upscaling factor for the preview")
    b.add_argument("--scale", type=float, default=1.0,
                   help="metres per block (>1 shrinks the model)")
    b.add_argument("--data-version", type=int, default=3465,
                   help="Minecraft DataVersion to embed (default 1.20.1)")
    b.set_defaults(func=_cmd_build)

    i = sub.add_parser("info", help="print dataset statistics")
    add_source_args(i)
    i.set_defaults(func=_cmd_info)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "preview", None) == "":
        args.preview = None
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
