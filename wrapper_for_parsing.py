from parse_emails import parsing_wrapper
from extract_body_features import body_wrapper
from extract_header_features import header_wrapper
from io_helpers import change_filename
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--input", "-i", nargs="+", help="The name of the file to fix", required=True)
parser.add_argument("--output", "-o", help="The name of the file to output to", required=False)
parser.add_argument("--debug", "-d", help="debug mode", action="store_true", required=False)
parser.add_argument("--sample", "-s", help="use a sample of files instead of all files from dir, specify number of samples desired", required=False)




def fully_process(infile, outfile, debug, sample):
    parsed_fname = parsing_wrapper(infile, outfile, debug, sample)
    body_features_fname, url_fname = body_wrapper(parsed_fname, change_filename(parsed_fname, "body_features", "json"), debug)
    header_features_fname = header_wrapper(parsed_fname, change_filename(parsed_fname, "header_features", "json"), debug)

    print(f"Parsed Filename: {os.path.basename(parsed_fname)}")
    print(f"Body Features Filename: {os.path.basename(body_features_fname)}")
    print(f"URL Features Filename: {os.path.basename(url_fname)}")
    print(f"Header Features Filename {os.path.basename(header_features_fname)}")

if __name__ == '__main__':
    args = parser.parse_args()
    infile = args.input
    outfile = args.output
    debug = args.debug
    sample = args.sample
    fully_process(infile, outfile, debug, sample)