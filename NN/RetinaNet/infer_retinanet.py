#!/usr/bin/env python
# coding: utf-8

# # Ïðîâåðêà ðàáîòû íåéðîñåòè äëÿ îáëàñòåé îäèíàêîâûõ òîâàðîâ
# ðèñîâàíèå êàðòèíîê
# âû÷èñëåíèå symmetric_best_dice

# In[1]:

inference_width = 1024
model_root = 'NN_results/retina_chars_72c04f'
model_weights = '/models/clr.007'

device = 'cuda:0'
#device = 'cpu'
cls_thresh = 0.3
nms_thresh = 0

fn = r'D:\Programming\Braille\Data\My\data\ola\IMG_5200.JPG'

import sys
sys.path.append('../..')
import local_config
sys.path.append(local_config.global_3rd_party)
from os.path import join
model_fn = join(local_config.data_path, model_root)

from ovotools.params import AttrDict
import numpy as np
import torch
import time
import copy
import PIL.ImageDraw
import PIL.ImageFont
import DSBI_invest.data
import create_model_retinanet
import pytorch_retinanet
import pytorch_retinanet.encoder
import postprocess

class BrailleInference:
    def __init__(self):

        params = AttrDict.load(model_fn + '.param.txt', verbose = True)
        params.data.net_hw = (inference_width,inference_width,) #(512,768) ###### (1024,1536) #
        params.data.batch_size = 1 #######
        params.augmentation = AttrDict(
            img_width_range=(inference_width, inference_width),
            stretch_limit = 0.0,
            rotate_limit=0,
        )

        self.model, collate_fn, loss = create_model_retinanet.create_model_retinanet(params, phase='train', device=device)
        self.model = self.model.to(device)
        self.model.load_state_dict(torch.load(model_fn + model_weights, map_location = 'cpu'))
        self.model.eval()
        print("Model loaded")

        self.preprocessor = DSBI_invest.data.ImagePreprocessor(params, mode = 'inference')
        self.encoder = pytorch_retinanet.encoder.DataEncoder(**params.model_params.encoder_params)

    def run(self, img_fn):
        print("run.preprocess")
        t = time.clock()
        img = PIL.Image.open(img_fn)
        np_img = np.asarray(img)

        aug_img = self.preprocessor.preprocess_and_augment(np_img)[0]
        input_data = self.preprocessor.to_normalized_tensor(aug_img)
        input_data = input_data.unsqueeze(0).to(device)
        print(time.clock() - t)
        print("run.model")
        t = time.clock()
        with torch.no_grad():
            (loc_preds, cls_preds) = self.model(input_data)
        print(time.clock() - t)
        print("run.postprocess")
        t = time.clock()
        h,w = input_data.shape[2:]
        boxes, labels, scores = self.encoder.decode(loc_preds[0].cpu().data, cls_preds[0].cpu().data, (w,h),
                                      cls_thresh = cls_thresh, nms_thresh = nms_thresh)
        lines = postprocess.boxes_to_lines(boxes, labels)

        aug_img = PIL.Image.fromarray(aug_img)
        raw_image = copy.deepcopy(aug_img)
        draw = PIL.ImageDraw.Draw(aug_img)
        fnt = PIL.ImageFont.truetype("arial.ttf", 8)
        fntA = PIL.ImageFont.truetype("arial.ttf", 28)
        out_text = []
        for ln in lines:
            s = ''
            for ch in ln.chars:
                s += ' ' * ch.spaces_before + ch.char
                draw.rectangle(list(ch.box), outline='green')
                chr = ch.char[:1]
                draw.text((ch.box[0]+5,ch.box[3]), chr, font=fntA, fill="black")
                #score = scores[i].item()
                #score = '{:.1f}'.format(score*10)
                #draw.text((box[0],box[3]+12), score, font=fnt, fill='green')
            out_text.append(s)
        print(time.clock() - t)
        return raw_image, aug_img, lines, out_text, self.to_dict(aug_img, lines)

    def to_dict(self, img, lines):
        '''
        generates dict for LabelMe json format
        :param img:
        :param lines:
        :return: dict
        '''
        shapes = []
        for ln in lines:
            for ch in ln.chars:
                chr = ch.char
                if not chr:
                    lbl = DSBI_invest.data.int_to_letter(ch.label.item(), 'SYM')
                    if lbl in {DSBI_invest.letters.markout_sign,
                               DSBI_invest.letters.num_sign,
                               DSBI_invest.letters.caps_sign}:
                        chr = lbl
                    else:
                        chr = "&"+DSBI_invest.data.int_to_label123(ch.label.item())
                shape = {
                    "label": chr,
                    "points": [[ch.box[0].item(), ch.box[1].item()],[ch.box[2].item(), ch.box[3].item()]],
                    "shape_type": "rectangle",
                    "line_color": None,
                    "fill_color": None,
                }
                shapes.append(shape)
        res = {"shapes": shapes,
               "imageHeight": img.height, "imageWidth": img.width, "imagePath": None, "imageData": None,
               "lineColor": None, "fillColor": None,
               }
        return res


if __name__ == '__main__':
    recognizer = BrailleInference()

    out_img, lines, out_text = recognizer.run(fn)

    for ln in out_text:
        print(ln)
    out_img.show()