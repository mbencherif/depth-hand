import os
import sys
# from importlib import import_module
import logging
import numpy as np
import tensorflow as tf
import progressbar
from functools import reduce
from utils.coder import file_pack
from utils.image_ops import tfplot_hmap2, tfplot_hmap3, tfplot_uomap


class train_dense_regre():
    def _train_iter(self, sess, ops, saver,
                    model_path, train_writer, valid_writer):
        valid_loss = np.inf
        from timeit import default_timer as timer
        from datetime import timedelta
        with file_pack() as filepack:
            epoch = 0
            time_all_s = timer()
            self.args.model_inst.start_train(filepack)
            while epoch < self.args.max_epoch:
                epoch += 1
                self.logger.info(
                    '**** Epoch #{:03d} ****'.format(epoch))
                sys.stdout.flush()

                split_beg, split_end = \
                    self.args.data_inst.next_valid_split()
                # print(split_beg, split_end)

                time_s = timer()
                self.logger.info('** Training **')
                self.args.model_inst.start_epoch_train(
                    split_beg, split_end)
                self.train_one_epoch(sess, ops, train_writer)
                self.logger.info('** Validating **')
                self.args.model_inst.start_epoch_valid(
                    split_beg, split_end)
                mean_loss = self.valid_one_epoch(
                    sess, ops, valid_writer)
                time_e = str(timedelta(
                    seconds=(timer() - time_s)))
                self.args.logger.info(
                    'Epoch #{:03d} processing time: {}'.format(
                        epoch, time_e))
                if mean_loss > (valid_loss * 1.1):
                    self.args.logger.info(
                        'Break due to validation loss starts to grow: {} --> {}'.format(
                            valid_loss, mean_loss))
                    break
                elif mean_loss > valid_loss:
                    self.args.logger.info(
                        'NOTE: validation loss starts to grow: {} --> {}'.format(
                            valid_loss, mean_loss))
                else:
                    # only save model when validation loss decrease
                    valid_loss = mean_loss
                    save_path = saver.save(sess, model_path)
                    self.logger.info(
                        'Model saved in file: {}'.format(save_path))
            self.args.model_inst.end_train()
            time_all_e = timer() - time_all_s
            self.args.logger.info(
                'Total training time: {} for {:d} epoches, average: {}.'.format(
                    str(timedelta(seconds=time_all_e)), epoch,
                    str(timedelta(seconds=(time_all_e / epoch)))))

    def train(self):
        self.logger.info('######## Training ########')
        tf.reset_default_graph()
        with tf.Graph().as_default(), \
                tf.device('/gpu:' + str(self.args.gpu_id)):
            frames_op, poses_op = \
                self.args.model_inst.placeholder_inputs()
            is_training_tf = tf.placeholder(
                tf.bool, shape=(), name='is_training')

            global_step = tf.train.create_global_step()

            pred_op, end_points = self.args.model_inst.get_model(
                frames_op, is_training_tf, self.args.bn_decay)
            shapestr = 'input: {}'.format(frames_op.shape)
            for ends in self.args.model_inst.end_point_list:
                net = end_points[ends]
                shapestr += '\n{}: {} = ({}, {})'.format(
                    ends, net.shape,
                    net.shape[0],
                    reduce(lambda x, y: x * y, net.shape[1:])
                )
            self.args.logger.info(
                'network structure:\n{}'.format(shapestr))
            loss_op = self.args.model_inst.get_loss(
                pred_op, poses_op, end_points)
            # regre_error = tf.sqrt(loss_op * 2)
            regre_error = loss_op
            tf.summary.scalar('regression_error', regre_error)

            learning_rate = self.get_learning_rate(global_step)
            tf.summary.scalar('learning_rate', learning_rate)

            num_j = self.args.model_inst.out_dim
            hmap2_echt_op = tf.expand_dims(tfplot_hmap2(
                frames_op[0, ..., 0][::4, ::4],
                poses_op[0, ..., num_j - 1]), axis=0)
            tf.summary.image('hmap2_echt/', hmap2_echt_op, max_outputs=1)
            hmap2_pred_op = tf.expand_dims(tfplot_hmap2(
                frames_op[0, ..., 0][::4, ::4],
                pred_op[0, ..., num_j - 1]), axis=0)
            tf.summary.image('hmap2_pred/', hmap2_pred_op, max_outputs=1)
            num_j *= 2
            hmap3_echt_op = tf.expand_dims(tfplot_hmap3(
                frames_op[0, ..., 0][::4, ::4],
                poses_op[0, ..., num_j - 1]), axis=0)
            tf.summary.image('hmap3_echt/', hmap3_echt_op, max_outputs=1)
            hmap3_pred_op = tf.expand_dims(tfplot_hmap3(
                frames_op[0, ..., 0][::4, ::4],
                pred_op[0, ..., num_j - 1]), axis=0)
            tf.summary.image('hmap3_pred/', hmap3_pred_op, max_outputs=1)
            uomap_echt_op = tf.expand_dims(tfplot_uomap(
                frames_op[0, ..., 0],
                poses_op[0, ..., -3:]),
                axis=0)
            tf.summary.image('uomap_echt/', uomap_echt_op, max_outputs=1)
            uomap_pred_op = tf.expand_dims(tfplot_uomap(
                frames_op[0, ..., 0],
                pred_op[0, ..., -3:]),
                axis=0)
            tf.summary.image('uomap_pred/', uomap_pred_op, max_outputs=1)

            optimizer = tf.train.AdamOptimizer(learning_rate)
            # train_op = optimizer.minimize(
            #     loss_op, global_step=global_step)
            from tensorflow.contrib import slim
            train_op = slim.learning.create_train_op(
                loss_op, optimizer,
                update_ops=tf.get_collection(tf.GraphKeys.UPDATE_OPS),
                global_step=global_step)
            # from tensorflow.python.ops import control_flow_ops
            # train_op = slim.learning.create_train_op(
            #     loss_op, optimizer, global_step=global_step)
            # update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
            # if update_ops:
            #     updates = tf.group(*update_ops)
            #     loss_op = control_flow_ops.with_dependencies(
            #         [updates], loss_op)

            saver = tf.train.Saver(max_to_keep=4)

            config = tf.ConfigProto()
            config.gpu_options.allow_growth = True
            config.allow_soft_placement = True
            config.log_device_placement = False
            with tf.Session(config=config) as sess:
                model_path = self.args.model_inst.ckpt_path
                if self.args.retrain:
                    init = tf.global_variables_initializer()
                    sess.run(init)
                else:
                    saver.restore(sess, model_path)
                    self.logger.info(
                        'model restored from: {}.'.format(
                            model_path))

                summary_op = tf.summary.merge_all()
                train_writer = tf.summary.FileWriter(
                    os.path.join(self.args.log_dir_t, 'train'),
                    sess.graph)
                valid_writer = tf.summary.FileWriter(
                    os.path.join(self.args.log_dir_t, 'valid'))

                ops = {
                    'batch_frame': frames_op,
                    'batch_poses': poses_op,
                    'is_training': is_training_tf,
                    'summary_op': summary_op,
                    'step': global_step,
                    'train_op': train_op,
                    'loss_op': loss_op,
                    'pred_op': pred_op
                }
                self._train_iter(
                    sess, ops, saver,
                    model_path, train_writer, valid_writer)

    def train_one_epoch(self, sess, ops, train_writer):
        """ ops: dict mapping from string to tf ops """
        batch_count = 0
        loss_sum = 0
        while True:
            batch_data = self.args.model_inst.fetch_batch()
            if batch_data is None:
                break
            feed_dict = {
                ops['batch_frame']: batch_data['batch_frame'],
                ops['batch_poses']: batch_data['batch_poses'],
                ops['is_training']: True
            }
            summary, step, _, loss_val, pred_val = sess.run(
                [ops['summary_op'], ops['step'], ops['train_op'],
                    ops['loss_op'], ops['pred_op']],
                feed_dict=feed_dict)
            loss_sum += loss_val / self.args.batch_size
            if batch_count % 10 == 0:
                if 'locor' == self.args.model_inst.net_type:
                    self.args.model_inst.debug_compare(
                        pred_val, self.logger)
                    did = np.random.randint(0, self.args.batch_size)
                    self.args.model_inst._debug_draw_prediction(
                        did, pred_val[did, ...]
                    )
                # elif 'poser' == self.args.model_inst.net_type:
                #     self.args.model_inst.debug_compare(
                #         pred_val, self.logger)
                self.logger.info(
                    'batch {} training loss: {}'.format(
                        batch_count, loss_val))
            if batch_count % 100 == 0:
                train_writer.add_summary(summary, step)
            batch_count += 1
        mean_loss = loss_sum / batch_count
        self.args.logger.info(
            'epoch training mean loss: {:.4f}'.format(
                mean_loss))
        return mean_loss

    def valid_one_epoch(self, sess, ops, valid_writer):
        """ ops: dict mapping from string to tf ops """
        batch_count = 0
        loss_sum = 0
        while True:
            batch_data = self.args.model_inst.fetch_batch()
            if batch_data is None:
                break
            feed_dict = {
                ops['batch_frame']: batch_data['batch_frame'],
                ops['batch_poses']: batch_data['batch_poses'],
                ops['is_training']: False
            }
            summary, step, loss_val, pred_val = sess.run(
                [ops['summary_op'], ops['step'],
                    ops['loss_op'], ops['pred_op']],
                feed_dict=feed_dict)
            loss_sum += loss_val / self.args.batch_size
            if batch_count % 10 == 0:
                if 'locor' == self.args.model_inst.net_type:
                    self.args.model_inst.debug_compare(
                        pred_val, self.logger)
                # elif 'poser' == self.args.model_inst.net_type:
                #     self.args.model_inst.debug_compare(
                #         pred_val, self.logger)
                self.logger.info(
                    'batch {} validate loss: {}'.format(
                        batch_count, loss_val))
            if batch_count % 100 == 0:
                valid_writer.add_summary(summary, step)
            batch_count += 1
        mean_loss = loss_sum / batch_count
        self.args.logger.info(
            'epoch validate mean loss: {:.4f}'.format(
                mean_loss))
        return mean_loss

    def evaluate(self):
        self.logger.info('######## Evaluating ########')
        tf.reset_default_graph()
        with tf.Graph().as_default(), \
                tf.device('/gpu:' + str(self.args.gpu_id)):
            # sequential evaluate, suited for streaming
            frames_op, poses_op = \
                self.args.model_inst.placeholder_inputs(1)
            is_training_tf = tf.placeholder(
                tf.bool, shape=(), name='is_training')

            pred_op, end_points = self.args.model_inst.get_model(
                frames_op, is_training_tf, self.args.bn_decay)
            loss_op = self.args.model_inst.get_loss(
                pred_op, poses_op, end_points)

            saver = tf.train.Saver()

            config = tf.ConfigProto()
            config.gpu_options.allow_growth = True
            config.allow_soft_placement = True
            config.log_device_placement = False
            with tf.Session(config=config) as sess:
                model_path = self.args.model_inst.ckpt_path
                self.logger.info(
                    'restoring model from: {} ...'.format(model_path))
                saver.restore(sess, model_path)
                self.logger.info('model restored.')

                ops = {
                    'batch_frame': frames_op,
                    'batch_poses': poses_op,
                    'is_training': is_training_tf,
                    'loss_op': loss_op,
                    'pred_op': pred_op
                }

                with file_pack() as filepack:
                    writer = self.args.model_inst.start_evaluate(
                        filepack)
                    self.eval_one_epoch_write(sess, ops, writer)
                self.args.model_inst.end_evaluate(
                    self.args.data_inst, self.args)

    def eval_one_epoch_write(self, sess, ops, writer):
        batch_count = 0
        loss_sum = 0
        num_stores = self.args.model_inst.store_size
        timerbar = progressbar.ProgressBar(
            maxval=num_stores,
            widgets=[
                progressbar.Percentage(),
                ' ', progressbar.Bar('=', '[', ']'),
                ' ', progressbar.ETA()]
        ).start()
        while True:
            batch_data = self.args.model_inst.fetch_batch(1)
            if batch_data is None:
                break
            feed_dict = {
                ops['batch_frame']: batch_data['batch_frame'],
                ops['batch_poses']: batch_data['batch_poses'],
                ops['is_training']: False
            }
            loss_val, pred_val = sess.run(
                [ops['loss_op'], ops['pred_op']],
                feed_dict=feed_dict)
            self.args.model_inst.evaluate_batch(
                writer, pred_val
            )
            loss_sum += loss_val
            timerbar.update(batch_count)
            batch_count += 1
        timerbar.finish()
        mean_loss = loss_sum / batch_count
        self.args.logger.info(
            'epoch evaluate mean loss: {:.4f}'.format(
                mean_loss))
        return mean_loss

    def get_learning_rate(self, global_step):
        learning_rate = tf.train.exponential_decay(
            self.args.learning_rate,
            global_step,
            self.args.decay_step,
            self.args.decay_rate,
            staircase=True
        )
        learning_rate = tf.maximum(learning_rate, 1e-6)
        return learning_rate

    def __init__(self, args, new_log=True):
        self.args = args
        self.logger = logging.getLogger('train')
