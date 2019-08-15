import tensorflow as tf
from tflearn.layers.conv import global_avg_pool
from tensorflow.contrib.layers import batch_norm, flatten
from tensorflow.contrib.layers import xavier_initializer
from tensorflow.contrib.framework import arg_scope
from data_provider.cifar10 import *

import neuralgym as ng
import argparse

# Hyperparameter
# growth_k = 24
# nb_block = 3 # how many (dense block + Transition Layer) ?
# init_learning_rate = 1e-4
# epsilon = 1e-4 # AdamOptimizer epsilon
# dropout_rate = 0.2


# nb_layers_121 = [6, 12, 24, 16] # how many bottlenecks in each dense block
# nb_layers_169 = [6, 12, 32, 32]
# nb_layers_201 = [6, 12, 48, 32]
# nb_layers_264 = [6, 12, 64, 48]

# Momentum Optimizer will use
# nesterov_momentum = 0.9
# weight_decay = 1e-4

# Label & batch_size
# batch_size = 64

# iteration = 782
# batch_size * iteration = data_set_number

# test_iteration = 10

# total_epochs = 300

def conv_layer(input, filter, kernel, stride=1, layer_name="conv"):
    with tf.name_scope(layer_name):
        network = tf.layers.conv2d(inputs=input, use_bias=False, filters=filter, kernel_size=kernel, strides=stride, padding='SAME')
        return network

def Global_Average_Pooling(x, stride=1):
    """
    width = np.shape(x)[1]
    height = np.shape(x)[2]
    pool_size = [width, height]
    return tf.layers.average_pooling2d(inputs=x, pool_size=pool_size, strides=stride) # The stride value does not matter
    It is global average pooling without tflearn
    """

    return global_avg_pool(x, name='Global_avg_pooling')
    # But maybe you need to install h5py and curses or not


def Batch_Normalization(x, training, scope):
    with arg_scope([batch_norm],
                   scope=scope,
                   updates_collections=None,
                   decay=0.9,
                   center=True,
                   scale=True,
                   zero_debias_moving_mean=True) :
        return tf.cond(training,
                       lambda : batch_norm(inputs=x, is_training=training, reuse=None),
                       lambda : batch_norm(inputs=x, is_training=training, reuse=True))

def Drop_out(x, rate, training) :
    return tf.layers.dropout(inputs=x, rate=rate, training=training)

def Relu(x):
    return tf.nn.relu(x)

def Average_pooling(x, pool_size=[2,2], stride=2, padding='VALID'):
    return tf.layers.average_pooling2d(inputs=x, pool_size=pool_size, strides=stride, padding=padding)


def Max_Pooling(x, pool_size=[3,3], stride=2, padding='VALID'):
    return tf.layers.max_pooling2d(inputs=x, pool_size=pool_size, strides=stride, padding=padding)

def Concatenation(layers) :
    return tf.concat(layers, axis=3)

def Linear(x, class_num) :
    return tf.layers.dense(inputs=x, units=class_num, name='linear')

def Evaluate(sess, test_iteration):
    test_acc = 0.0
    test_loss = 0.0
    test_pre_index = 0
    add = 1000

    for it in range(test_iteration):
        test_batch_x = test_x[test_pre_index: test_pre_index + add]
        test_batch_y = test_y[test_pre_index: test_pre_index + add]
        test_pre_index = test_pre_index + add

        test_feed_dict = {
            x: test_batch_x,
            label: test_batch_y,
            learning_rate: epoch_learning_rate,
            training_flag: False
        }

        loss_, acc_ = sess.run([cost, accuracy], feed_dict=test_feed_dict)

        test_loss += loss_ / 10.0
        test_acc += acc_ / 10.0

    summary = tf.Summary(value=[tf.Summary.Value(tag='test_loss', simple_value=test_loss),
                                tf.Summary.Value(tag='test_accuracy', simple_value=test_acc)])

    return test_acc, test_loss, summary

class DenseNet():
    def __init__(self, x, nb_blocks, filters, training, dropout_rate, model_type=None):
        self.nb_blocks = nb_blocks
        self.filters = filters
        self.training = training
        self.model_type = model_type
        self.dropout_rate = dropout_rate
        self.model = self.Dense_net(x)


    def bottleneck_layer(self, x, scope):
        # print(x)
        with tf.name_scope(scope):
            x = Batch_Normalization(x, training=self.training, scope=scope+'_batch1')
            x = Relu(x)
            x = conv_layer(x, filter=4 * self.filters, kernel=[1,1], layer_name=scope+'_conv1')
            x = Drop_out(x, rate=self.dropout_rate, training=self.training)

            x = Batch_Normalization(x, training=self.training, scope=scope+'_batch2')
            x = Relu(x)
            x = conv_layer(x, filter=self.filters, kernel=[3,3], layer_name=scope+'_conv2')
            x = Drop_out(x, rate=self.dropout_rate, training=self.training)

            # print(x)

            return x

    def transition_layer(self, x, scope):
        with tf.name_scope(scope):
            x = Batch_Normalization(x, training=self.training, scope=scope+'_batch1')
            x = Relu(x)
            # x = conv_layer(x, filter=self.filters, kernel=[1,1], layer_name=scope+'_conv1')
            
            # https://github.com/taki0112/Densenet-Tensorflow/issues/10
            
            in_channel = x.get_shape().as_list()[-1]
            x = conv_layer(x, filter=in_channel*0.5, kernel=[1,1], layer_name=scope+'_conv1')
            x = Drop_out(x, rate=self.dropout_rate, training=self.training)
            x = Average_pooling(x, pool_size=[2,2], stride=2)

            return x

    def dense_block(self, input_x, nb_layers, layer_name):
        with tf.name_scope(layer_name):
            layers_concat = list()
            layers_concat.append(input_x)
            x = self.bottleneck_layer(input_x, scope=layer_name + '_bottleN_' + str(0))

            layers_concat.append(x)

            for i in range(nb_layers - 1):
                x = Concatenation(layers_concat)
                x = self.bottleneck_layer(x, scope=layer_name + '_bottleN_' + str(i + 1))
                layers_concat.append(x)

            x = Concatenation(layers_concat)

            return x

    def Dense_net(self, input_x):
        x = conv_layer(input_x, filter=2 * self.filters, kernel=[7,7], stride=2, layer_name='conv0')
        # x = Max_Pooling(x, pool_size=[3,3], stride=2)
        block_order = arg.nb_layers_order

        for i in range(self.nb_blocks):
            # 6 -> 12 -> 48
            print("the number of %d is %d \n" % (i, block_order[i]))
            x = self.dense_block(input_x=x, nb_layers=block_order[i], layer_name='dense_'+str(i))
            x = self.transition_layer(x, scope='trans_'+str(i))

        # x = self.dense_block(input_x=x, nb_layers=6, layer_name='dense_1')
        # x = self.transition_layer(x, scope='trans_1')
        #
        # x = self.dense_block(input_x=x, nb_layers=12, layer_name='dense_2')
        # x = self.transition_layer(x, scope='trans_2')
        #
        # x = self.dense_block(input_x=x, nb_layers=48, layer_name='dense_3')
        # x = self.transition_layer(x, scope='trans_3')

        x = self.dense_block(input_x=x, nb_layers=block_order[-1], layer_name='dense_final')



        # 100 Layer
        x = Batch_Normalization(x, training=self.training, scope='linear_batch')
        x = Relu(x)
        x = Global_Average_Pooling(x)
        x = flatten(x)
        x = Linear(x, arg.class_num)


        # x = tf.reshape(x, [-1, 10])
        return x


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='para/setting_1.yml', help='Config Document')
    Config_args = parser.parse_args()
    arg = ng.Config(Config_args.config)

    if arg.dataset_type == 'cifar-100':
        train_x, train_y, test_x, test_y = prepare_data_cifar100(arg.image_size, arg.img_channels, arg.data_dir)
    elif arg.dataset_type == 'cifar-10':
        train_x, train_y, test_x, test_y = prepare_data_cifar10(arg.image_size, arg.img_channels, arg.data_dir)
    else:
        train_x, train_y, test_x, test_y = prepare_data_cifar100(arg.image_size, arg.img_channels)
    train_x, test_x = color_preprocessing(train_x, test_x)

    # image_size = 32, img_channels = 3, class_num = 10 in cifar10
    x = tf.placeholder(tf.float32, shape=[None, arg.image_size, arg.image_size, arg.img_channels])
    label = tf.placeholder(tf.float32, shape=[None, arg.class_num])

    training_flag = tf.placeholder(tf.bool)


    learning_rate = tf.placeholder(tf.float32, name='learning_rate')

    logits = DenseNet(x=x, nb_blocks=arg.nb_block, filters=arg.growth_k,
                      training=training_flag, dropout_rate=arg.dropout_rate).model
    cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=label, logits=logits))

    """
    l2_loss = tf.add_n([tf.nn.l2_loss(var) for var in tf.trainable_variables()])
    optimizer = tf.train.MomentumOptimizer(learning_rate=learning_rate, momentum=arg.nesterov_momentum, use_nesterov=True)
    train = optimizer.minimize(cost + l2_loss * arg.weight_decay)
    
    In paper, use MomentumOptimizer
    init_learning_rate = 0.1
    
    but, I'll use AdamOptimizer
    """
    l2_loss = tf.add_n([tf.nn.l2_loss(var) for var in tf.trainable_variables()])

    if arg.optimizer == 'Adam':
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate, epsilon=arg.epsilon)
        train = optimizer.minimize(cost + l2_loss * arg.weight_decay)
    elif arg.optimizer == 'Momentum':
        optimizer = tf.train.MomentumOptimizer(learning_rate=learning_rate, momentum=arg.nesterov_momentum,
                                               use_nesterov=True)
        train = optimizer.minimize(cost + l2_loss * arg.weight_decay)


    correct_prediction = tf.equal(tf.argmax(logits, 1), tf.argmax(label, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

    saver = tf.train.Saver(tf.global_variables())

    with tf.Session() as sess:
        ckpt = tf.train.get_checkpoint_state(arg.checkpoint)
        if ckpt and tf.train.checkpoint_exists(ckpt.model_checkpoint_path):
            saver.restore(sess, ckpt.model_checkpoint_path)
        else:
            sess.run(tf.global_variables_initializer())

        summary_writer = tf.summary.FileWriter(arg.logs, sess.graph)

        epoch_learning_rate = arg.init_learning_rate
        for epoch in range(1, arg.total_epochs + 1):
            for point in range(len(arg.lr_decay_point)):
                if epoch == (arg.total_epochs * arg.lr_decay_point[point]):
                    epoch_learning_rate = epoch_learning_rate / 10

            pre_index = 0
            train_acc = 0.0
            train_loss = 0.0


            for step in range(1, arg.iteration + 1):
                if pre_index+arg.batch_size < 50000 :
                    batch_x = train_x[pre_index : pre_index+arg.batch_size]
                    batch_y = train_y[pre_index : pre_index+arg.batch_size]
                else :
                    batch_x = train_x[pre_index : ]
                    batch_y = train_y[pre_index : ]

                batch_x = data_augmentation(batch_x)

                train_feed_dict = {
                    x: batch_x,
                    label: batch_y,
                    learning_rate: epoch_learning_rate,
                    training_flag : True
                }

                _, batch_loss = sess.run([train, cost], feed_dict=train_feed_dict)
                batch_acc = accuracy.eval(feed_dict=train_feed_dict)

                train_loss += batch_loss
                train_acc += batch_acc
                pre_index += arg.batch_size

                if step == arg.iteration :
                    train_loss /= arg.iteration # average loss
                    train_acc /= arg.iteration # average accuracy

                    train_summary = tf.Summary(value=[tf.Summary.Value(tag='train_loss', simple_value=train_loss),
                                                      tf.Summary.Value(tag='train_accuracy', simple_value=train_acc)])

                    test_acc, test_loss, test_summary = Evaluate(sess, arg.test_iteration)

                    summary_writer.add_summary(summary=train_summary, global_step=epoch)
                    summary_writer.add_summary(summary=test_summary, global_step=epoch)
                    summary_writer.flush()

                    line = "epoch: %d/%d, train_loss: %.4f, train_acc: %.4f, test_loss: %.4f, test_acc: %.4f \n" % (
                        epoch, arg.total_epochs, train_loss, train_acc, test_loss, test_acc)
                    print(line)

                    with open(arg.summary, 'a') as f :
                        f.write(line)



            saver.save(sess=sess, save_path='./model/dense.ckpt')
