import os
import os.path as osp
import numpy as np
from PIL import Image
import cv2
from torch.utils import data
import torch
import datasets.edge_utils as edge_utils

import logging
from config import cfg

num_classes = 16
ignore_label = 255
root = cfg.DATASET.iSAID_DIR

label2trainid = {0: 255, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8, 10: 9,
                 11: 10, 12: 11, 13: 12, 14: 13, 15: 14}
id2cat = {0: 'background', 1: 'ship', 2: 'store_tank', 3: 'baseball_diamond', 4: 'tennis_court', 5: 'basketball_court',
          6: 'Ground_Track_Field', 7: 'Bridge', 8: 'Large_Vehicle', 9: 'Small_Vehicle', 10: 'Helicopter',
          11: 'Swimming_pool', 12: 'Roundabout', 13: 'Soccer_ball_field', 14: 'plane', 15: 'Harbor'}

palette = [0, 0, 0, 0, 0, 63, 0, 63, 63, 0, 63, 0, 0, 63, 127, 0, 63, 191, 0, 63, 255, 0, 127, 63, 0, 127, 127,
           0, 0, 127, 0, 0, 191, 0, 0, 255, 0, 191, 127, 0, 127, 191, 0, 127, 255, 0, 100, 155]

zero_pad = 256 * 3 - len(palette)
for i in range(zero_pad):
    palette.append(0)

def colorize_mask(mask):
    new_mask = Image.fromarray(mask.astype(np.int8)).convert('P')
    new_mask.putpalette(palette)
    return new_mask

def make_dataset(quality, mode, hardnm=0):
    all_tokens = []

    assert quality == 'semantic'
    assert mode in ['train', 'val', 'test', 'val_ori', 'val1000']

    image_path = osp.join(root, mode, 'images')
    mask_path = osp.join(root, mode, 'masks')

    c_tokens = os.listdir(image_path)
    c_tokens.sort()
    mask_tokens = [c_token.replace('.png', '_instance_color_RGB.png') for c_token in c_tokens]

    for img_token, mask_token in zip(c_tokens, mask_tokens):
        token = (osp.join(image_path, img_token), osp.join(mask_path, mask_token))
        all_tokens.append(token)
    logging.info(f'iSAID has a total of {len(all_tokens)} images in {mode} phase')

    logging.info(f'iSAID-{mode}: {len(all_tokens)} images')

    return all_tokens


class ISAIDDataset(data.Dataset):

    def __init__(self, quality, mode, maxSkip=0, joint_transform_list=None,
                 transform=None, target_transform=None, dump_images=False,
                 class_uniform_pct=None, class_uniform_title=0, test=False,
                 cv_split=None, scf=None, hardnm=0, edge_map=False, thicky=8):

        self.quality = quality
        self.mode = mode
        self.maxSkip = maxSkip
        self.joint_transform_list = joint_transform_list
        self.transform = transform
        self.target_transform = target_transform
        self.dump_images = dump_images
        self.class_uniform_pct = class_uniform_pct
        self.class_uniform_title = class_uniform_title
        if cv_split:
            self.cv_split = cv_split
            assert cv_split < cfg.DATASET.CV_SPLITS
        self.scf = scf
        self.hardnm = hardnm
        self.edge_map = edge_map

        self.data_tokens = make_dataset(quality, mode, hardnm)
        self.thicky = thicky

        assert len(self.data_tokens), 'Found 0 images please check the dataset'

    def __getitem__(self, index):

        token = self.data_tokens[index]
        image_path, mask_path = token

        image, mask = Image.open(image_path).convert('RGB'), Image.open(mask_path)
        image_name = osp.splitext(osp.basename(image_path))[0]

        if self.joint_transform_list is not None:
            for idx, xform in enumerate(self.joint_transform_list):
                image, mask = xform(image, mask)

            # Debug
        if self.dump_images:
            outdir = '../../dump_imgs_{}'.format(self.mode)
            os.makedirs(outdir, exist_ok=True)
            out_img_fn = os.path.join(outdir, image_name + '.png')
            out_msk_fn = os.path.join(outdir, image_name + '_mask.png')
            mask_img = colorize_mask(np.array(mask))
            image.save(out_img_fn)
            mask_img.save(out_msk_fn)

        if self.transform is not None:
            image = self.transform(image)

        if self.target_transform is not None:
            mask = self.target_transform(mask)


        if self.edge_map:
            boundary = self.get_boundary(mask, thicky=self.thicky)
            body = self.get_body(mask, boundary)
            return image, mask, body, boundary, image_name


        return image, mask, image_name

    def __len__(self):
        return len(self.data_tokens)

    def build_epoch(self):
        pass

    @staticmethod
    def get_boundary(mask, thicky=8):
        tmp = mask.data.numpy().astype('uint8')
        contour, _ = cv2.findContours(tmp, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        boundary = np.zeros_like(tmp)
        boundary = cv2.drawContours(boundary, contour, -1, 1, thicky)
        boundary = boundary.astype(np.float)
        return boundary

    @staticmethod
    def get_body(mask, edge):
        edge_valid = edge == 1
        body = mask.clone()
        body[edge_valid] = ignore_label
        return body
