Write-Host "Starting 1,000,000 game simulation..."
python Network_training/train_genetic.py

Write-Host "Simulation Complete! Packaging Kaggle submission..."
Remove-Item -Recurse -Force submission -ErrorAction Ignore
New-Item -ItemType Directory -Force -Path submission
Copy-Item -Path Network_training/main.py -Destination submission/main.py
Copy-Item -Path Network_training/optimized_weights.json -Destination submission/optimized_weights.json
Copy-Item -Path data/deck.csv -Destination submission/deck.csv
tar -czvf submission.tar.gz -C submission .

Write-Host "submission.tar.gz successfully built and ready for upload!"
