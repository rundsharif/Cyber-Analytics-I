from csv import DictWriter
import ujson
import os
import argparse
from io_helpers import get_sample, change_filename

parser = argparse.ArgumentParser()
parser.add_argument("--input", "-i", help="The name of the file to fix", required=True)
parser.add_argument("--output", "-o", help="The name of the file to output to", required=False)
parser.add_argument("--debug", "-d", help="debug mode", action="store_true", required=False)

def get_all_headers(infile):
    with open(infile, 'r') as f:
        k_set = set()
        for line in f:
            tempd = ujson.loads(line)
            k_set.update(list(tempd.keys()))
        return list(k_set)

    

if __name__ == '__main__':
    args = parser.parse_args()
    infile = args.input
    outfile = args.output
    debug = args.debug
    if not outfile:
        outfile = "default_out.json"
    elif os.path.exists(outfile):
        if input(f"please enter anything if you want to first delete the existing output file {outfile}: \n"):
            os.remove(outfile)
    heads = get_all_headers(infile)
    with open(infile, 'r') as f, open(outfile, "w") as wf:
        dw = DictWriter(wf, fieldnames=heads)
        dw.writeheader()
        for line in f:
            try:
                dw.writerow(ujson.loads(line))
            except ValueError as e:
                print(line)
                raise e