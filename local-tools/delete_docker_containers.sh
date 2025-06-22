#!/bin/bash

# List all Docker images
images=$(docker containers -q)

# Check if there are any images
if [ -z "$images" ]; then
  echo "No Docker containers found."
else
  # Delete all Docker images
  echo "Deleting all Docker images..."
  docker rm -f $images
  echo "All Docker images have been deleted."
fi
