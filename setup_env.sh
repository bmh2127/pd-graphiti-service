#!/bin/bash

# Setup script for Phase 4.1 - Integration with Real Graphiti

echo "Setting up pd-graphiti-service environment for Phase 4.1..."

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
# OpenAI Configuration - REPLACE WITH YOUR ACTUAL KEY
OPENAI_API_KEY=your_openai_key_here

# Neo4j Configuration (using graphiti's defaults)
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphiti123
NEO4J_PORT=7687

# Graphiti Configuration
GRAPHITI_GROUP_ID=pd_target_discovery

# Logging Configuration
LOG_LEVEL=INFO
EOF
    echo "Created .env file. Please edit it to add your OpenAI API key."
else
    echo ".env file already exists."
fi

echo "Starting Neo4j database..."
cd docker && docker-compose up -d neo4j

echo "Waiting for Neo4j to be ready..."
sleep 30

echo "Checking Neo4j status..."
docker-compose exec neo4j cypher-shell -u neo4j -p graphiti123 "MATCH () RETURN count(*) as node_count" || echo "Neo4j not ready yet, but should be starting..."

echo "Setup complete! Neo4j should be running on:"
echo "  - Web interface: http://localhost:7474"
echo "  - Bolt connection: bolt://localhost:7687"
echo "  - Username: neo4j"
echo "  - Password: graphiti123"
echo ""
echo "Next steps:"
echo "1. Edit .env file to add your OpenAI API key"
echo "2. Run the test script to verify integration"