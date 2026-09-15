package com.example.media_downloader

import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.net.Uri

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

import java.io.File
import java.io.FileInputStream
import java.io.OutputStream
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {

    private val CHANNEL = "mp34_downloader/media_store"

    private val executor = Executors.newSingleThreadExecutor()

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL
        ).setMethodCallHandler { call, result ->

            when (call.method) {

                "saveFile" -> {

                    val filePath = call.argument<String>("filePath")
                    val fileName = call.argument<String>("fileName")
                    val type = call.argument<String>("type")

                    if (filePath.isNullOrBlank()) {
                        result.error(
                            "INVALID_PATH",
                            "File path is missing.",
                            null
                        )
                        return@setMethodCallHandler
                    }

                    if (fileName.isNullOrBlank()) {
                        result.error(
                            "INVALID_NAME",
                            "File name is missing.",
                            null
                        )
                        return@setMethodCallHandler
                    }

                    if (type != "audio" && type != "video") {
                        result.error(
                            "INVALID_TYPE",
                            "Media type must be audio or video.",
                            null
                        )
                        return@setMethodCallHandler
                    }

                    executor.execute {

                        try {

                            val uri = saveToMediaStore(
                                filePath = filePath,
                                fileName = fileName,
                                type = type
                            )

                            runOnUiThread {
                                result.success(uri.toString())
                            }

                        } catch (e: Exception) {

                            runOnUiThread {
                                result.error(
                                    "MEDIASTORE_ERROR",
                                    e.message ?: "Failed to save media.",
                                    null
                                )
                            }
                        }
                    }
                }

                else -> {
                    result.notImplemented()
                }
            }
        }
    }

    private fun saveToMediaStore(
        filePath: String,
        fileName: String,
        type: String
    ): Uri {

        val sourceFile = File(filePath)

        if (!sourceFile.exists()) {
            throw Exception(
                "Source file does not exist:\n$filePath"
            )
        }

        if (sourceFile.length() <= 0) {
            throw Exception(
                "Source file is empty."
            )
        }

        /*
         * Android 10 (API 29) and newer:
         *
         * Use MediaStore with RELATIVE_PATH and IS_PENDING.
         */
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {

            val resolver = applicationContext.contentResolver

            val collection: Uri

            val relativePath: String

            val mimeType: String

            if (type == "audio") {

                collection =
                    MediaStore.Audio.Media.getContentUri(
                        MediaStore.VOLUME_EXTERNAL_PRIMARY
                    )

                relativePath =
                    Environment.DIRECTORY_MUSIC +
                            "/MP34 Downloader"

                mimeType = "audio/mpeg"

            } else {

                collection =
                    MediaStore.Video.Media.getContentUri(
                        MediaStore.VOLUME_EXTERNAL_PRIMARY
                    )

                relativePath =
                    Environment.DIRECTORY_MOVIES +
                            "/MP34 Downloader"

                mimeType = "video/mp4"
            }

            val values = ContentValues().apply {

                put(
                    MediaStore.MediaColumns.DISPLAY_NAME,
                    fileName
                )

                put(
                    MediaStore.MediaColumns.MIME_TYPE,
                    mimeType
                )

                put(
                    MediaStore.MediaColumns.RELATIVE_PATH,
                    relativePath
                )

                put(
                    MediaStore.MediaColumns.IS_PENDING,
                    1
                )
            }

            println("NATIVE MEDIASTORE:")
            println("Collection: $collection")
            println("File name: $fileName")
            println("Relative path: $relativePath")
            println("MIME: $mimeType")
            println("Source size: ${sourceFile.length()} bytes")

            val uri = resolver.insert(
                collection,
                values
            )
                ?: throw Exception(
                    "Android MediaStore could not create the media entry."
                )

            println("MediaStore URI created:")
            println(uri.toString())

            try {

                resolver.openOutputStream(uri).use { outputStream ->

                    if (outputStream == null) {
                        throw Exception(
                            "Android could not open the MediaStore output stream."
                        )
                    }

                    copyFile(
                        sourceFile = sourceFile,
                        outputStream = outputStream
                    )
                }

                println(
                    "File copied successfully to MediaStore."
                )

                /*
                 * The file is now complete.
                 *
                 * Setting IS_PENDING to 0 publishes it so other
                 * media applications can see it.
                 */
                val completedValues = ContentValues().apply {

                    put(
                        MediaStore.MediaColumns.IS_PENDING,
                        0
                    )
                }

                resolver.update(
                    uri,
                    completedValues,
                    null,
                    null
                )

                println(
                    "MediaStore file published successfully."
                )

                return uri

            } catch (e: Exception) {

                /*
                 * If anything goes wrong, remove the incomplete
                 * MediaStore entry.
                 */
                try {
                    resolver.delete(
                        uri,
                        null,
                        null
                    )
                } catch (_: Exception) {
                    // Ignore cleanup errors.
                }

                throw e
            }
        }

        /*
         * This app targets modern Android devices.
         *
         * Android versions below 10 use a different storage model.
         * We fail clearly rather than silently saving somewhere
         * unexpected.
         */
        throw Exception(
            "This version of MP34 Downloader requires Android 10 or newer."
        )
    }

    private fun copyFile(
        sourceFile: File,
        outputStream: OutputStream
    ) {

        FileInputStream(sourceFile).use { inputStream ->

            val buffer = ByteArray(1024 * 1024)

            var totalBytes = 0L

            while (true) {

                val bytesRead =
                    inputStream.read(buffer)

                if (bytesRead == -1) {
                    break
                }

                outputStream.write(
                    buffer,
                    0,
                    bytesRead
                )

                totalBytes += bytesRead

                println(
                    "MediaStore copied: $totalBytes bytes"
                )
            }

            outputStream.flush()
        }
    }

    override fun onDestroy() {

        executor.shutdown()

        super.onDestroy()
    }
}