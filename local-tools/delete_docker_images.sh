#!/bin/bash

# List all Docker images
images=$(docker images -q)

# Check if there are any images
if [ -z "$images" ]; then
  echo "No Docker images found."
else
  # Delete all Docker images
  echo "Deleting all Docker images..."
  docker rmi -f $images
  echo "All Docker images have been deleted."
fi
