import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.spenbridge.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.spenbridge.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 3
        versionName = "1.1.0-rc2"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        create("audit") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".uiaudit"
            matchingFallbacks += listOf("debug")
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    sourceSets.getByName("audit").java.srcDir("src/debug/java")
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    testOptions { unitTests.isReturnDefaultValues = true }
    buildFeatures {
        viewBinding = true
    }
}

kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) } }

dependencies {
    testImplementation("junit:junit:4.13.2")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
