// Kotlin 2.4 requires R8 >= 9.1.29, including when AGP itself remains 8.5.2.
buildscript {
    repositories { google(); mavenCentral() }
    dependencies { classpath("com.android.tools:r8:9.1.57") }
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
        resolutionStrategy.force("com.android.tools:r8:9.1.57")
    }
}

plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.4.21" apply false
}

allprojects {
    dependencyLocking { lockAllConfigurations() }
}
