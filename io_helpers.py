import os
from random import randint
def change_filename(fname, ext: str, suffix = ""):
    if suffix:
        suffix = "_" + suffix
    b_name = os.path.basename(fname)
    p_path = os.path.dirname(fname)
    split_name = b_name.split(".")
    n_name = split_name[0] + suffix + "." + ext
    return os.path.join(p_path, n_name)

def get_sample(big_list, samp_size):
    sample_start = randint(1, len(big_list)-samp_size)
    small_list = big_list[sample_start:sample_start + samp_size]

    return small_list