import argparse
import ujson
from collections import Counter

parser = argparse.ArgumentParser()
parser.add_argument("--input", "-i", help="The name of the file to fix", required=True)
parser.add_argument("--pull-headers", "-p", nargs="+", help="the headers that we want to extract data from", required=True)
parser.add_argument("--disregard", "-d", default=False, action='store_true', help="(Optional) If instead of specifying headers you WANT to inspect, this inverts it to ignore the headers you specify. Useful for when you want all but one header analyzed")



def get_counter(fname, headers, disregard = False):
    if disregard:
        all_k_set = get_all_keys(fname)
        headers = list(all_k_set - set(headers))


    out_d = {h:Counter() for h in headers}
    print(f"Checking Keys: {headers}")
    with open(fname, "r") as f:
        for i, line in enumerate(f, 1):
            temp_d = ujson.loads(line)
            for h in headers:
                if h in temp_d.keys():
                    out_d[h][temp_d[h]] += 1
            line_count = i
        #print(out_d)
        for k in out_d:
            total_count = sum(out_d[k].values())
            check_sanity(line_count, total_count, k)

def get_all_keys(fname):
    k_set = set()
    with open(fname, "r") as f:
        for line in f:
            d = ujson.loads(line)
            k_set.update(d.keys())
        return k_set



def check_sanity(lc, tc, key):
    dif = lc - tc
    print(f"Total Line Count: {lc}\nTotal lines with key '{key}':{tc}")
    if dif > 0:
        print(f"% of Lines without data in '{key}': {round(float((dif / lc)*100), 2)}%")
    else:
        print(f"No Discrepency for '{key}'!\n")

if __name__ == "__main__":
    args = parser.parse_args()
    fname = args.input
    headers= args.pull_headers
    disregard= args.disregard
    get_counter(fname, headers, disregard)