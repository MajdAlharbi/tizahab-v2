# Contributing to Tizahab

Use the [local setup guide](README.md) to prepare an isolated development environment.
Keep changes focused on destination discovery, trip planning and the existing
Arabic/English experience.

## Before submitting changes

- Preserve existing user selections, trip ownership and migration compatibility.
- Add meaningful regression coverage for functional changes. Run the core checks
  listed in the setup guide against isolated databases and synthetic accounts.
- Follow the existing Django/templates/JavaScript structure; format Python with Black.
- Check both Arabic RTL and English LTR when changing visible content or navigation.
- Use verified destination information and appropriately licensed images with attribution.
- Keep `.env`, databases, credentials and local verification artifacts out of Git.
- Summarize the resulting behavior and relevant validation in your pull request.

Update the [API reference](API_DOCUMENTATION.md) for API changes and the
[deployment guide](DEPLOYMENT.md) for operational configuration changes.
Keep the root README focused on the product.

The original graduation project was a team effort. Preserve its contributors,
attribution and Git history, and distinguish subsequent V2 contributions accurately.
