# User Profiler API — PowerShell examples
# Start the server first: uvicorn main:app --reload

$BASE = "http://localhost:8000"

# ---------------------------------------------------------------------------
# 0. List all user IDs
# ---------------------------------------------------------------------------
Write-Host "`n--- 0. List all users ---"
Invoke-RestMethod -Method Get -Uri "$BASE/users" | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 1. Create a minimal user  (required fields only)
# ---------------------------------------------------------------------------
Write-Host "`n--- 1. Create minimal user ---"
$user1 = Invoke-RestMethod -Method Post -Uri "$BASE/user" `
  -ContentType "application/json" `
  -Body (@{
    name        = "Alice"
    surname     = "Rossi"
    age         = 34
    email       = "alice.rossi@example.com"
    affiliation = "University of Milan"
  } | ConvertTo-Json -Depth 10)
$user1 | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 2. Create a full user  (location + ORCID + publications + session)
# ---------------------------------------------------------------------------
Write-Host "`n--- 2. Create full user ---"
$user2 = Invoke-RestMethod -Method Post -Uri "$BASE/user" `
  -ContentType "application/json" `
  -Body (@{
    name        = "Bob"
    surname     = "Verdi"
    age         = 41
    email       = "bob.verdi@example.com"
    affiliation = "CNR"
    location    = @{ city = "Rome"; country = "Italy" }
    orcid       = @{
      id           = "0000-0002-1825-0097"
      keywords     = @(@{ value = "machine learning" }, @{ value = "knowledge graphs" })
      publications = @(@{
        title   = "Graph-Based User Profiling"
        doi     = "10.1000/xyz123"
        journal = "Data Science Journal"
        year    = 2023
        authors = @(@{ fullName = "Bob Verdi" }, @{ fullName = "Alice Rossi" })
      })
    }
    sessions = @(@{
      sessionId = "sess-001"
      startTime = "2024-03-10T09:00:00"
      endTime   = "2024-03-10T09:45:00"
      queries   = @(
        @{ text = "knowledge graph embedding"; typedAt = "2024-03-10T09:05:00" },
        @{ text = "GNN survey 2023";            typedAt = "2024-03-10T09:20:00" }
      )
    })
  } | ConvertTo-Json -Depth 10)
$user2 | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 3. Get a user by ID
# ---------------------------------------------------------------------------
Write-Host "`n--- 3. Get user by ID ---"
$userId = $user2.userId
Invoke-RestMethod -Method Get -Uri "$BASE/user/$userId" | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 4. Get a user that does not exist
# ---------------------------------------------------------------------------
Write-Host "`n--- 4. Get non-existent user ---"
Invoke-RestMethod -Method Get -Uri "$BASE/user/nonexistent-id-000" | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 5. Edit a user — update scalar fields
# ---------------------------------------------------------------------------
Write-Host "`n--- 5. Edit scalar fields ---"
Invoke-RestMethod -Method Patch -Uri "$BASE/user/$userId" `
  -ContentType "application/json" `
  -Body (@{
    age         = 42
    affiliation = "CNR - Institute of Cognitive Sciences"
  } | ConvertTo-Json -Depth 10) | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 6. Edit a user — replace location
# ---------------------------------------------------------------------------
Write-Host "`n--- 6. Replace location ---"
Invoke-RestMethod -Method Patch -Uri "$BASE/user/$userId" `
  -ContentType "application/json" `
  -Body (@{
    location = @{ city = "Turin"; country = "Italy" }
  } | ConvertTo-Json -Depth 10) | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 7. Edit a user — replace sessions list
# ---------------------------------------------------------------------------
Write-Host "`n--- 7. Replace sessions ---"
Invoke-RestMethod -Method Patch -Uri "$BASE/user/$userId" `
  -ContentType "application/json" `
  -Body (@{
    sessions = @(@{
      sessionId = "sess-002"
      startTime = "2024-04-01T14:00:00"
      queries   = @(@{ text = "transformer architectures"; typedAt = "2024-04-01T14:03:00" })
    })
  } | ConvertTo-Json -Depth 10) | ConvertTo-Json -Depth 10

# ---------------------------------------------------------------------------
# 8. Edit a non-existent user
# ---------------------------------------------------------------------------
Write-Host "`n--- 8. Edit non-existent user ---"
Invoke-RestMethod -Method Patch -Uri "$BASE/user/nonexistent-id-000" `
  -ContentType "application/json" `
  -Body (@{ age = 99 } | ConvertTo-Json) | ConvertTo-Json -Depth 10
