# Copyright (c) Meta Platforms, Inc. and affiliates.

import argparse
from pathlib import Path
import shutil
import zipfile

import numpy as np
from tqdm.auto import tqdm

# from ... import logger
# from ...osm.tiling import TileManager
# from ...osm.viz import GeoPlotter
# from ...utils.geo import BoundaryBox, Projection
# from ...utils.io import download_file, DATA_URL
# from .utils import parse_gps_file
# from .dataset import BoreasDataModule
import sys
sys.path.append('/home/classlab2/root/OrienterNet')
from maploc import logger
from maploc.osm.tiling import TileManager
from maploc.osm.viz import GeoPlotter
from maploc.utils.geo import BoundaryBox, Projection
from maploc.utils.io import download_file, DATA_URL
from maploc.data.oxford.utils import parse_gps_file
from maploc.data.oxford.dataset import OxfordDataModule

split_files = ["test1_files.txt", "test2_files.txt", "train_files.txt"]


def prepare_osm(
    data_dir,
    osm_path,
    output_path,
    tile_margin=128,
    ppm=2,
):
    all_latlon = []
    for gps_path in data_dir.glob("*/GPS/*.txt"):#boreas的gps数据需要一次性解析多行
        all_latlon.append(parse_gps_file(gps_path)[0])
    if not all_latlon:
        raise ValueError(f"Cannot find any GPS file in {data_dir}.")
    all_latlon = np.stack(all_latlon)
    
    projection = Projection.from_points(all_latlon)
    all_xy = projection.project(all_latlon)
    bbox_map = BoundaryBox(all_xy.min(0), all_xy.max(0)) + tile_margin

    plotter = GeoPlotter()
    plotter.points(all_latlon, "red", name="GPS")
    plotter.bbox(projection.unproject(bbox_map), "blue", "tiling bounding box")
    plotter.fig.write_html(data_dir / "split_boreas1114.html")
    print(ppm)
    tile_manager = TileManager.from_bbox(
        projection,
        bbox_map,
        ppm,
        path=osm_path,
    )
    tile_manager.save(output_path)
    return tile_manager


def download(data_dir: Path):
    data_dir.mkdir(exist_ok=True, parents=True)
    this_dir = Path(__file__).parent

    seqs = set()
    for f in split_files:
        shutil.copy(this_dir / f, data_dir)
        with open(this_dir / f, "r") as fid:
            info = fid.read()
        for line in info.split("\n"):
            if line:
                seq = line.split()[0].split("/")[1][: -len("_sync")]
                seqs.add(seq)
    dates = {"_".join(s.split("_")[:3]) for s in seqs}
    logger.info("Downloading data for %d sequences in %d dates", len(seqs), len(dates))

    for seq in tqdm(seqs):
        logger.info("Working on %s.", seq)
        date = "_".join(seq.split("_")[:3])
        url = f"https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/{seq}/{seq}_sync.zip"
        seq_dir = data_dir / date / f"{seq}_sync"
        if seq_dir.exists():
            continue
        zip_path = download_file(url, data_dir)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(data_dir)
        # Delete unused files to save space.
        for image_index in [0, 1, 3]:
            shutil.rmtree(seq_dir / f"image_0{image_index}")
        shutil.rmtree(seq_dir / "velodyne_points")
        Path(zip_path).unlink()
        break

    for date in tqdm(dates):
        url = (
            f"https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/{date}_calib.zip"
        )
        zip_path = download_file(url, data_dir)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(data_dir)
        Path(zip_path).unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_dir", type=Path, default=Path(OxfordDataModule.default_cfg["data_dir"])
    )
    parser.add_argument("--pixel_per_meter", type=int, default=2)
    parser.add_argument("--generate_tiles", default=True,action="store_true")#生成tiles
    args = parser.parse_args()

    args.data_dir.mkdir(exist_ok=True, parents=True)
    #提前下载好数据
    #download(args.data_dir)  

    tiles_path = args.data_dir / OxfordDataModule.default_cfg["tiles_filename"]
    tiles_path = args.data_dir / "oxford_ppm1.pkl"
    if args.generate_tiles:
        logger.info("Generating the map tiles.")
        osm_filename = "karlsruhe.osm"#查找对应的oms地图
        # osm_path = args.data_dir / osm_filename
        osm_path = Path("/home/classlab2/root/OrienterNet/datasets/OSM/oxford1.osm")
        if not osm_path.exists():
            logger.info("Downloading OSM raw data.")
            download_file(DATA_URL + f"/osm/{osm_filename}", osm_path)
        if not osm_path.exists():
            raise FileNotFoundError(f"No OSM data file at {osm_path}.")
        prepare_osm(args.data_dir, osm_path, tiles_path, ppm=args.pixel_per_meter)#osm数据：提供osm地址或者根据gps的坐标下载（应该是不行的）
        (args.data_dir / ".downloaded").touch()
    else:
        logger.info("Downloading pre-generated map tiles.")
        download_file(DATA_URL + "/tiles/kitti.pkl", tiles_path)#没有提供的话需要生成对应的地图瓦片
