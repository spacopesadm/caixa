plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "br.com.spacopes.caixa"
    compileSdk = 34

    defaultConfig {
        applicationId = "br.com.spacopes.caixa"
        minSdk = 24
        targetSdk = 34
        versionCode = (System.getenv("VERSAO") ?: "1").toInt()
        versionName = System.getenv("VERSAO") ?: "1"
    }

    buildFeatures {
        buildConfig = true
    }

    flavorDimensions += "app"
    productFlavors {
        create("caixa") {
            dimension = "app"
            buildConfigField("boolean", "VENDEDOR", "false")
            resValue("string", "app_name", "Painel do Caixa")
        }
        create("vendedor") {
            dimension = "app"
            applicationId = "br.com.spacopes.entregas"
            buildConfigField("boolean", "VENDEDOR", "true")
            resValue("string", "app_name", "Entregas Spaço Pés")
        }
    }

    signingConfigs {
        create("loja") {
            storeFile = file("../loja.keystore")
            storePassword = "spacopes"
            keyAlias = "loja"
            keyPassword = "spacopes"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("loja")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}
