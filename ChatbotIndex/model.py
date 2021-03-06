import cPickle as pickle
import numpy as np
import argparse

# sys.path.append(os.path.join(os.path.dirname(__file__), '../../build/python'))
from singa import layer
from singa import loss
from singa import device
from singa import tensor 
from singa import optimizer   
from singa import initializer
from singa.proto import model_pb2
from tqdm import tnrange
from word2tensor import load_data,numpy2tensors,convert,labelconvert

             
      
def get_lr(epoch):
    return 0.001 / float(1 << (epoch / 50)) 
    
# SGD with L2 gradient normalization 
vocab_size=7000
opt = optimizer.RMSProp(constraint=optimizer.L2Constraint(5))
cuda = device.create_cuda_gpu() 
encoder = layer.LSTM(name='lstm', hidden_size=32, num_stacks=1, dropout=0.5, input_sample_shape=(vocab_size,))
decoder = layer.LSTM(name='lstm', hidden_size=32, num_stacks=1, dropout=0.5, input_sample_shape=(vocab_size,)) 
encoder.to_device(cuda)
decoder.to_device(cuda)
encoder_w = encoder.param_values()[0]
encoder_w.uniform(-0.08, 0.08)
decoder_w = decoder.param_values()[0]
decoder_w.uniform(-0.08, 0.08)

dense = layer.Dense('dense', vocab_size, input_sample_shape=(32,))
dense.to_device(cuda)
dense_w = dense.param_values()[0]
dense_b = dense.param_values()[1]
initializer.uniform(dense_w, dense_w.shape[0], 0)
dense_b.set_value(0)

g_dense_w = tensor.Tensor(dense_w.shape, cuda)
g_dense_b = tensor.Tensor(dense_b.shape, cuda)

lossfun = loss.SoftmaxCrossEntropy()
batch_size=50
train_loss = 0
maxlength=22
num_train_batch=100
metadata, idx_q, idx_a=load_data()
for epoch in range(1):
    bar =range(num_train_batch)
    for b in range (num_train_batch):
        batcha=idx_a[b * batch_size: (b + 1) * batch_size]
        batchq=idx_q[b * batch_size: (b + 1) * batch_size]
        inputs=convert(batchq,batch_size,20,vocab_size,cuda)
        inputs.append(tensor.Tensor())
        inputs.append(tensor.Tensor())
        outputs = encoder.forward(model_pb2.kTrain, inputs)[-2:]
        inputs2=convert(batcha,batch_size,22,vocab_size,cuda)[:-1]
        inputs2.extend(outputs)
        labels=labelconvert(batcha,cuda)[1:]
        grads=[]
        batch_loss=0
        g_dense_w.set_value(0.0)
        g_dense_b.set_value(0.0)
        outputs2 = decoder.forward(model_pb2.kTrain, inputs2)[0:-2]
        for output,label in zip(outputs2,labels):
            act=dense.forward(model_pb2.kTrain, output)
            lvalue=lossfun.forward(model_pb2.kTrain,act,label)
            batch_loss += lvalue.l1()

            grad=lossfun.backward()
            grad/=batch_size
            grad,gwb=dense.backward(model_pb2.kTrain,grad)
            grads.append(grad)
            g_dense_w += gwb[0]
            g_dense_b += gwb[1]
        train_loss += batch_loss
        print '\nbatch loss is %f' % (batch_loss / maxlength)
        grads.append(tensor.Tensor())
        grads.append(tensor.Tensor())
        g_rnn_w = decoder.backward(model_pb2.kTrain, grads)[1][0]
        dense_w, dense_b = dense.param_values()
        opt.apply_with_lr(epoch, get_lr(epoch), g_rnn_w,decoder_w,'decoderw')
        opt.apply_with_lr(epoch, get_lr(epoch), g_dense_w, dense_w, 'dense_w')
        opt.apply_with_lr(epoch, get_lr(epoch), g_dense_b, dense_b, 'dense_b')
    print '\nEpoch %d, train loss is %f' % (epoch, train_loss /num_train_batch / maxlength)
