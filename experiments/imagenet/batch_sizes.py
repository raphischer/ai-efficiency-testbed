import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from util import execute

BATCH_SIZE_FILE = os.path.join(os.path.dirname(__file__), 'batch_sizes.json')

arch_test_code = """
import os
import tensorflow as tf
gpu_devices = tf.config.list_physical_devices('GPU')
if gpu_devices: # override with GPU information
    print(tf.config.experimental.get_device_details(gpu_devices[0]).get('device_name', 'Unknown GPU'))
else:
    os.chdir("$DIR")
    from util import get_processor_name
    print(get_processor_name())
""".replace('$DIR', os.path.dirname(__file__))

def lookup_batch_size(model):
    try:
        # identify architecture currently used
        for output in execute(['python', '-c', arch_test_code]):
            architecture = output.replace('\n', '')
        # look up batch size
        with open(BATCH_SIZE_FILE, 'r') as bf:
            batch_sizes = json.load(bf)
            return batch_sizes[architecture][model]
    except Exception as e:
        return None
    
def find_ideal_batch_size(model, nogpu, data_dir, max_tries=5):
    batch_size_tests = [1, 2, 4, 8, 16, 32, 64]
    if nogpu:
        batch_size_tests = [4, 8, 16, 32, 64, 128, 256, 512]
    optimal, fastest = min(batch_size_tests), np.inf
    for batch_size in batch_size_tests:
        success, iter = False, 0
        while not success and iter < max_tries-1:
            iter += 1
            t0 = time.time()
            try: # running the util script as main will perform a single inference experiment
                for path in execute(['python', os.path.join(os.path.dirname(__file__), 'data_and_model_loading.py'), '--model', model, '--batch-size', str(batch_size),
                                    '--datadir', data_dir, '--max_batch_size', str(max(batch_size_tests))]):
                    if 'sparse_categorical_accuracy' in path:
                        print(path[:-1], end="\r")
                time.sleep(5)
                success = True
            except Exception: # test failed for some reason
                time.sleep(5)
        if success:
            t1 = time.time()
            print(f'\n\n{str(batch_size):<4} {t1-t0:4.3f} ({iter} tries)\n\n')
            if t1-t0 < fastest:
                optimal = batch_size
                fastest = t1-t0
        else:
            print(f'\n\n{str(batch_size):<4} failed with {iter} tries\n\n')
    return optimal

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Extend the batch size file with the ideal batch sizes obtained for the given experiment summary file.")
    parser.add_argument("--experiment", default="imagenet_0_2025-02-04_03-09-17.csv")
    parser.add_argument("--override", default=False)
    args = parser.parse_args()

    # load already available batch sizes
    db = pd.read_csv(args.experiment)
    db = db[db["status"] == "FINISHED"]
    db = db[['params.architecture', 'params.model', 'params.batch_size']].dropna()
    if os.path.isfile(BATCH_SIZE_FILE):
        with open(BATCH_SIZE_FILE, 'r') as bf:
            batch_sizes = json.load(bf)
    else:
        batch_sizes = {}

    # store batch sizes
    for (arch, mod), batch_size in db.groupby(['params.architecture', 'params.model']):
        if arch not in batch_sizes:
            batch_sizes[arch] = {}
        assert batch_size.shape[0] == 1
        if mod not in batch_sizes[arch] or args.override:
            print('Storing / overriding batch size for', arch, mod)
            batch_sizes[arch][mod] = int(batch_size['params.batch_size'].iloc[0])

    # write updated batch size file
    with open(BATCH_SIZE_FILE, 'w') as bf:
        json.dump(batch_sizes, bf, indent=4)

    
