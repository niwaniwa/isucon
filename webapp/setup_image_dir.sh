#!/bin/bash

# Create image directory if it doesn't exist
mkdir -p public/image

# Set proper permissions for the image directory
# Make it writable by the app container
chmod 777 public/image

echo "Image directory created and permissions set"