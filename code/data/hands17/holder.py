import os
import numpy as np
from colour import Color
import cv2
from timeit import default_timer as timer
from random import random
from multiprocessing.dummy import Pool as ThreadPool
# import multiprocessing
# from multiprocessing import Manager as ThreadManager
import ops as dataops
import io as dataio


class hands17holder:
    """ Pose class for Hands17 dataset """

    # dataset info
    data_dir = ''
    training_images = ''
    frame_images = ''
    training_cropped = ''
    training_annot_origin = ''
    training_annot_cleaned = ''
    training_annot_shuffled = ''
    training_annot_cropped = ''
    training_annot_train = ''
    training_annot_test = ''
    training_annot_predict = ''
    frame_bbox = ''

    # num_training = int(957032)
    num_training = int(992)
    # num_training = int(96)
    tt_split = int(64)
    range_train = np.zeros(2, dtype=np.int)
    range_test = np.zeros(2, dtype=np.int)

    # cropped & resized training images
    image_size = [640, 480]
    crop_size = 96

    # camera info
    focal = (475.065948, 475.065857)
    centre = (315.944855, 245.287079)
    # fx = 475.065948
    # fy = 475.065857
    # cx = 315.944855
    # cy = 245.287079

    join_name = [
        'Wrist',
        'TMCP', 'IMCP', 'MMCP', 'RMCP', 'PMCP',
        'TPIP', 'TDIP', 'TTIP',
        'IPIP', 'IDIP', 'ITIP',
        'MPIP', 'MDIP', 'MTIP',
        'RPIP', 'RDIP', 'RTIP',
        'PPIP', 'PDIP', 'PTIP'
    ]

    join_num = 21
    join_type = ('W', 'T', 'I', 'M', 'R', 'P')
    join_color = (
        # Color('cyan'),
        Color('black'),
        Color('magenta'),
        Color('blue'),
        Color('lime'),
        Color('yellow'),
        Color('red')
    )
    join_id = (
        (1, 6, 7, 8),
        (2, 9, 10, 11),
        (3, 12, 13, 14),
        (4, 15, 16, 17),
        (5, 18, 19, 20)
    )
    bone_id = (
        ((0, 1), (1, 6), (6, 11), (11, 16)),
        ((0, 2), (2, 7), (7, 12), (12, 17)),
        ((0, 3), (3, 8), (8, 13), (13, 18)),
        ((0, 4), (4, 9), (9, 14), (14, 19)),
        ((0, 5), (5, 10), (10, 15), (15, 20))
    )
    bbox_color = Color('orange')

    def remove_out_frame_annot(self):
        self.num_training = int(0)
        with open(self.training_annot_cleaned, 'w') as writer, \
                open(self.training_annot_origin, 'r') as reader:
            for annot_line in reader.readlines():
                _, pose_mat, rescen = dataio.parse_line_pose(annot_line)
                pose2d = dataops.get2d(pose_mat)
                if 0 > np.min(pose2d):
                    continue
                if 0 > np.min(self.image_size - pose2d):
                    continue
                writer.write(annot_line)
                self.num_training += 1

    def shuffle_annot(self):
        with open(self.training_annot_cleaned, 'r') as source:
            data = [(random(), line) for line in source]
        data.sort()
        with open(self.training_annot_shuffled, 'w') as target:
            for _, line in data:
                target.write(line)

    def split_evaluation_images(self):
        with open(self.training_annot_cropped, 'r') as f:
            lines = [x.strip() for x in f.readlines()]
        with open(self.training_annot_train, 'w') as f:
            for line in lines[self.range_train[0]:self.range_train[1]]:
                f.write(line + '\n')
        with open(self.training_annot_test, 'w') as f:
            for line in lines[self.range_test[0]:self.range_test[1]]:
                # name = re.search(r'(image_D\d+\.png)', line).group(1)
                # shutil.move(
                #     os.path.join(self.training_cropped, name),
                #     os.path.join(self.evaluate_cropped, name))
                f.write(line + '\n')

    def get_rect_crop_resize(self, annot_line):
        """
            Returns:
                p3z_crop: projected 2d coordinates, and original z on the 3rd column
        """
        img_name, pose_mat, rescen = dataio.parse_line_pose(annot_line)
        img = dataio.read_image(
            os.path.join(self.training_images, img_name))
        pose2d = self.get2d(pose_mat)
        rect = dataops.get_rect(pose2d, 0.25)
        rs = self.crop_size / rect[1, 1]
        rescen = np.append(rs, rect[0, :])
        p2d_crop = (pose2d - rect[0, :]) * rs
        p3z_crop = np.hstack((
            p2d_crop, np.array(pose_mat[:, 2].reshape(-1, 1)) * rs
        ))
        img_crop = img[
            int(np.floor(rect[0, 1])):int(np.ceil(rect[0, 1] + rect[1, 1])),
            int(np.floor(rect[0, 0])):int(np.ceil(rect[0, 0] + rect[1, 0]))
        ]
        # try:
        # img_crop_resize = spmisc.imresize(
        #     img_crop, (self.crop_size, self.crop_size), interp='bilinear')
        # img_crop_resize = spndim.interpolation.zoom(img_crop, rs)
        # img_crop_resize = img_crop_resize[0:self.crop_size, 0:self.crop_size]
        img_crop_resize = cv2.resize(
            img_crop, (self.crop_size, self.crop_size))
        # except:
        #     print(np.hstack((pose_mat, pose2d)))
        # print(np.max(img_crop), np.max(img_crop_resize), img_crop_resize.shape)

        return img_name, img_crop_resize, p3z_crop, rescen

    def crop_resize_save(self, annot_line, messages=None):
        img_name, img_crop, p3z_crop, rescen = self.get_rect_crop_resize(
            annot_line)
        img_crop[1 > img_crop] = 9999  # max distance set to 10m
        dataio.save_image(
            os.path.join(self.training_cropped, img_name),
            img_crop
        )
        # hands17.draw_hist_random(self.training_cropped, img_name)
        out_list = np.append(p3z_crop.flatten(), rescen.flatten()).flatten()
        crimg_line = ''.join("%12.4f" % x for x in out_list)
        pose_l = img_name + crimg_line + '\n'
        if messages is not None:
            messages.put(pose_l)
        return pose_l

    def crop_resize_training_images(self):
        if not os.path.exists(self.training_cropped):
            os.makedirs(self.training_cropped)
        with open(self.training_annot_cropped, 'w') as crop_writer:
            with open(self.training_annot_shuffled, 'r') as fanno:
                for line_number, annot_line in enumerate(fanno):
                    pose_l = self.crop_resize_save(annot_line)
                    crop_writer.write(pose_l)
                    # break

    class mt_queue_writer:
        @staticmethod
        def listener(file_name, messages):
            with open(file_name, 'w') as writer:
                while 1:
                    m = messages.get()
                    if m == '\n':
                        break
                    print(m)
                    writer.write(m)

    def crop_resize_training_images_mt(self):
        if not os.path.exists(self.training_cropped):
            os.makedirs(self.training_cropped)
        # thread_manager = ThreadManager()
        # messages = thread_manager.Queue()
        # thread_pool = ThreadPool(multiprocessing.cpu_count() + 2)
        # watcher = thread_pool.apply_async(
        #     mt_queue_writer.listener,
        #     (self.training_annot_cropped, messages))
        # jobs = []
        # with open(self.training_annot_shuffled, 'r') as fanno:
        #     annot_line = fanno.readline()
        #     job = thread_pool.apply_async(
        #         hands17.crop_resize_save, (annot_line, messages))
        #     jobs.append(job)
        # for job in jobs:
        #     job.get()
        # messages.put('\n')
        # thread_pool.close()
        thread_pool = ThreadPool()
        with open(self.training_annot_shuffled, 'r') as fanno:
            annot_list = [line for line in fanno if line]
        with open(self.training_annot_cropped, 'w') as writer:
            for result in thread_pool.map(self.crop_resize_save, annot_list):
                # (item, count) tuples from worker
                writer.write(result)
        thread_pool.close()
        thread_pool.join()

    def init_data(self, data_dir, out_dir, rebuild=False):
        self.data_dir = data_dir
        self.training_images = os.path.join(data_dir, 'training/images')
        self.frame_images = os.path.join(data_dir, 'frame/images')
        self.training_cropped = os.path.join(out_dir, 'cropped')
        self.training_annot_origin = os.path.join(
            data_dir, 'training/Training_Annotation.txt')
        self.training_annot_cleaned = os.path.join(
            out_dir, 'annotation.txt')
        self.training_annot_shuffled = os.path.join(
            out_dir, 'annotation_shuffled.txt')
        self.training_annot_cropped = os.path.join(
            out_dir, 'annotation_cropped.txt')
        self.training_annot_train = os.path.join(
            out_dir, 'training_training.txt')
        self.training_annot_test = os.path.join(
            out_dir, 'training_evaluate.txt')
        self.training_annot_predict = os.path.join(
            out_dir, 'training_predict.txt')
        self.frame_bbox = os.path.join(data_dir, 'frame/BoundingBox.txt')

        if rebuild or (not os.path.exists(self.training_annot_cleaned)):
            self.remove_out_frame_annot(self)
        else:
            self.num_training = int(sum(
                1 for line in open(self.training_annot_cleaned, 'r')))

        portion = int(self.num_training / self.tt_split)
        self.range_train[0] = int(0)
        self.range_train[1] = int(portion * (self.tt_split - 1))
        self.range_test[0] = self.range_train[1]
        self.range_test[1] = self.num_training
        print('splitted data: {} training, {} test.'.format(
            self.range_train, self.range_test))

        if rebuild or (not os.path.exists(self.training_annot_shuffled)):
            self.shuffle_annot(self)
        print('using shuffled data: {}'.format(
            self.training_annot_shuffled))

        # if rebuild:  # just over-write, this detete operation is slow
        #     if os.path.exists(self.training_cropped):
        #         shutil.rmtree(self.training_cropped)
        if (rebuild or (not os.path.exists(self.training_annot_cropped)) or
                (not os.path.exists(self.training_cropped))):
            print('running cropping code (be patient) ...')
            # time_s = timer()
            # hands17.crop_resize_training_images()
            # print('single tread time: {:.4f}'.format(timer() - time_s))
            time_s = timer()
            self.crop_resize_training_images_mt(self)
            print('multiprocessing time: {:.4f}'.format(timer() - time_s))
        print('using cropped and resized images: {}'.format(
            self.training_cropped))

        if (rebuild or (not os.path.exists(self.training_annot_train)) or
                (not os.path.exists(self.training_annot_test))):
            self.split_evaluation_images(self)
        print('images are splitted out for evaluation: {:d} portions'.format(
            self.tt_split))