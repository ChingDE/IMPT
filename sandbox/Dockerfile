FROM eclipse-temurin:17-jdk-jammy

# Maven
RUN apt-get update && apt-get install -y curl unzip git && \
    curl -fsSL https://downloads.apache.org/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz | \
    tar -xz -C /opt && \
    ln -s /opt/apache-maven-3.9.6/bin/mvn /usr/local/bin/mvn

# Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Pre-cache PIT plugin
RUN mvn dependency:get -Dartifact=org.pitest:pitest-maven:1.15.3 -q 2>/dev/null || true

# Stryker
RUN npm install -g @stryker-mutator/core @stryker-mutator/javascript-mutator \
    @stryker-mutator/jest-runner --quiet

WORKDIR /project
