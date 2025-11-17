import argparse
import ujson
from io_helpers import get_sample, get_all_files_from_dir, change_filename
import hashlib
import base64
import uuid

import boto3
from botocore.exceptions import NoCredentialsError, ClientError

# Create S3 client
s3 = boto3.client('s3')


parser = argparse.ArgumentParser()
parser.add_argument("--input", "-i", help="The name of the file to fix", required=True)
parser.add_argument("--bucket", "-b", help="bucket to upload to", required=False)
parser.add_argument("--upload", "-u", help="upload file", action="store_true", required=False)



def rebuild_attachments(infile, bucket, upload):
    c = 0
    with open(infile, "r") as f:
        for line in f:
            temp_d = ujson.loads(line)
            if "attachments" in temp_d:
                for attachment in temp_d["attachments"]:
                    if upload:
                        if c == 1:
                            exit()
                        # Upload the attachment data to S3
                        try:
                            # Generate a unique filename for the attachment
                            unique_filename = f"test_attachments/{temp_d["email_id"]}/{attachment['filename']}"
                            
                            # Upload the attachment data to S3
                            s3.put_object(Bucket=bucket, Key=unique_filename, Body=base64.b64decode(attachment["data_base64"]))
                            c += 1
                            
                        except ClientError as e:
                            print(f"Error uploading to S3: {e}")
                            continue



if __name__ == '__main__':
    args = parser.parse_args()
    infile = args.input
    bucket = args.bucket
    upload = args.upload
    rebuild_attachments(infile, bucket, upload)