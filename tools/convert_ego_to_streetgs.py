#!/usr/bin/env python3
"""Convert AlpaSim ego rig poses to StreetGS model-world coordinates.

The CSV contains poses only; controller body-frame velocity/control/reference
columns are deliberately not copied into a model-world pose CSV.
"""
import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
import yaml

POSE_FIELDS = ['timestamp_us', 'x', 'y', 'z', 'qx', 'qy', 'qz', 'qw']


def rigid_matrix(value, name):
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValueError(f'{name}必须是有限数值的4×4矩阵')
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8):
        raise ValueError(f'{name}最后一行必须是[0,0,0,1]')
    rotation = matrix[:3, :3]
    if not (np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) and
            np.isclose(np.linalg.det(rotation), 1, atol=1e-5)):
        raise ValueError(f'{name}必须是无缩放、无反射的刚体变换')
    return matrix


def load_transform(scene):
    scene = Path(scene).expanduser().resolve()
    registry = scene / 'l3-scenes.yaml' if scene.is_dir() else scene
    with registry.open(encoding='utf-8') as stream:
        manifest = yaml.safe_load(stream)
    coordinates = manifest['coordinates']
    as_from_l3 = rigid_matrix(coordinates['as_from_l3_basis'], 'as_from_l3_basis')
    if 'model_from_scene_l3' in coordinates:
        model_from_l3 = rigid_matrix(coordinates['model_from_scene_l3'], 'model_from_scene_l3')
    else:
        # Match the renderer's legacy translation-only bridge.
        translation = np.asarray(coordinates['streetgs_from_l3_translation_m'], dtype=float)
        if translation.shape != (3,) or not np.all(np.isfinite(translation)):
            raise ValueError('streetgs_from_l3_translation_m必须是有限三维平移')
        model_from_l3 = np.eye(4)
        model_from_l3[:3, 3] = translation
    return rigid_matrix(model_from_l3 @ np.linalg.inv(as_from_l3), 'model_from_alpasim')


def convert_pose(position, quaternion_xyzw, model_from_alpasim):
    position = np.asarray(position, dtype=float)
    quaternion = np.asarray(quaternion_xyzw, dtype=float)
    if position.shape != (3,) or not np.all(np.isfinite(position)):
        raise ValueError('位置必须是有限三维坐标')
    if quaternion.shape != (4,) or not np.all(np.isfinite(quaternion)) or np.linalg.norm(quaternion) < 1e-12:
        raise ValueError('姿态四元数必须有限且非零，顺序qx,qy,qz,qw')
    source = np.eye(4)
    source[:3, 3] = position
    source[:3, :3] = Rotation.from_quat(quaternion).as_matrix()
    target = model_from_alpasim @ source
    return target[:3, 3], Rotation.from_matrix(target[:3, :3]).as_quat()


def convert_csv(source, scene, output=None):
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve() if output else source.with_name(source.stem + '_streetgs.csv')
    if output == source:
        raise ValueError('输出不能覆盖输入轨迹')
    if output.exists():
        raise FileExistsError(f'输出已存在，请指定新的 --output: {output}')
    transform = load_transform(scene)
    rows = []
    previous_quaternion = None
    with source.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        missing = set(POSE_FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'输入CSV缺少字段: {sorted(missing)}')
        for index, row in enumerate(reader, start=2):
            try:
                int(row['timestamp_us'])  # retain the original timestamp text
                position, quaternion = convert_pose(
                    [float(row[k]) for k in ('x', 'y', 'z')],
                    [float(row[k]) for k in ('qx', 'qy', 'qz', 'qw')], transform)
            except (ValueError, TypeError) as error:
                raise ValueError(f'CSV第{index}行无效: {error}') from error
            if previous_quaternion is not None and np.dot(previous_quaternion, quaternion) < 0:
                quaternion = -quaternion
            previous_quaternion = quaternion
            values = [format(float(v), '.17g') for v in (*position, *quaternion)]
            rows.append(dict(zip(POSE_FIELDS, [row['timestamp_us'], *values])))
    if not rows:
        raise ValueError('输入CSV没有轨迹数据')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=POSE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output, len(rows), transform


def main():
    parser = argparse.ArgumentParser(description='AlpaSim自车执行轨迹 → StreetGS原生模型坐标系（位置+姿态）')
    parser.add_argument('--input', required=True, help='ego_trajectory.csv路径')
    parser.add_argument('--scene', required=True, help='对应场景目录或该场景的l3-scenes.yaml')
    parser.add_argument('--output', help='输出CSV，默认输入旁的*_streetgs.csv；拒绝覆盖已有文件')
    args = parser.parse_args()
    output, count, transform = convert_csv(args.input, args.scene, args.output)
    print(f'已转换 {count} 帧，单位m，四元数qx,qy,qz,qw；坐标系=StreetGS model world')
    print(f'输出: {output}')
    print('model_from_alpasim = model_from_scene_l3 @ inverse(as_from_l3_basis):')
    print(transform)


if __name__ == '__main__':
    main()
