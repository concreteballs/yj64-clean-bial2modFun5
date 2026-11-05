package org.blackmirror.blackmirror;

import java.io.File;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

/** Portable password-based AES-GCM encryption for private YJ-64 archives. */
public final class PrivateArchiveCrypto {
    private static final byte[] MAGIC = "YJ64P01\n".getBytes(StandardCharsets.US_ASCII);
    private static final int SALT_BYTES = 16;
    private static final int IV_BYTES = 12;
    private static final int ITERATIONS = 310000;
    private static final int TAG_BITS = 128;
    private static final long MAX_FILE_BYTES = 128L * 1024L * 1024L;

    private PrivateArchiveCrypto() {}

    private static SecretKey derive(char[] password, byte[] salt) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, 256);
        try {
            byte[] key = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                .generateSecret(spec).getEncoded();
            try {
                return new SecretKeySpec(key, "AES");
            } finally {
                java.util.Arrays.fill(key, (byte) 0);
            }
        } finally {
            spec.clearPassword();
        }
    }

    public static String encryptFile(String inputPath, String outputPath, String password) throws Exception {
        if (password == null || password.length() < 12) throw new IllegalArgumentException("Use a passphrase of at least 12 characters.");
        byte[] plain = Files.readAllBytes(new File(inputPath).toPath());
        if (plain.length == 0 || plain.length > MAX_FILE_BYTES) throw new IllegalArgumentException("Private archive size is outside the supported limit.");
        byte[] salt = new byte[SALT_BYTES];
        byte[] iv = new byte[IV_BYTES];
        SecureRandom random = new SecureRandom();
        random.nextBytes(salt);
        random.nextBytes(iv);
        char[] chars = password.toCharArray();
        byte[] encrypted;
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, derive(chars, salt), new GCMParameterSpec(TAG_BITS, iv));
            cipher.updateAAD(MAGIC);
            encrypted = cipher.doFinal(plain);
        } finally {
            java.util.Arrays.fill(chars, '\0');
            java.util.Arrays.fill(plain, (byte) 0);
        }
        ByteBuffer buffer = ByteBuffer.allocate(MAGIC.length + 4 + SALT_BYTES + IV_BYTES + encrypted.length);
        buffer.put(MAGIC).putInt(ITERATIONS).put(salt).put(iv).put(encrypted);
        File output = new File(outputPath);
        File parent = output.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new java.io.IOException("Cannot create output directory.");
        File temporary = new File(outputPath + ".tmp");
        try {
            Files.write(temporary.toPath(), buffer.array());
            if (output.exists() && !output.delete()) throw new java.io.IOException("Cannot replace encrypted archive.");
            if (!temporary.renameTo(output)) throw new java.io.IOException("Cannot finalize encrypted archive.");
        } finally {
            if (temporary.exists()) temporary.delete();
            java.util.Arrays.fill(encrypted, (byte) 0);
            java.util.Arrays.fill(buffer.array(), (byte) 0);
        }
        return output.getAbsolutePath();
    }

    public static String decryptFile(String inputPath, String outputPath, String password) throws Exception {
        if (password == null || password.length() < 1) throw new IllegalArgumentException("Passphrase is required.");
        byte[] encoded = Files.readAllBytes(new File(inputPath).toPath());
        if (encoded.length < MAGIC.length + 4 + SALT_BYTES + IV_BYTES + 16 || encoded.length > MAX_FILE_BYTES + 128) {
            throw new IllegalArgumentException("Encrypted archive has an invalid size.");
        }
        byte[] plain = null;
        try {
            ByteBuffer buffer = ByteBuffer.wrap(encoded);
            byte[] magic = new byte[MAGIC.length];
            buffer.get(magic);
            if (!java.util.Arrays.equals(magic, MAGIC)) throw new IllegalArgumentException("This is not a YJ-64 encrypted private archive.");
            int iterations = buffer.getInt();
            if (iterations != ITERATIONS) throw new IllegalArgumentException("Unsupported archive key-derivation version.");
            byte[] salt = new byte[SALT_BYTES];
            byte[] iv = new byte[IV_BYTES];
            buffer.get(salt).get(iv);
            byte[] ciphertext = new byte[buffer.remaining()];
            buffer.get(ciphertext);
            char[] chars = password.toCharArray();
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, derive(chars, salt), new GCMParameterSpec(TAG_BITS, iv));
                cipher.updateAAD(MAGIC);
                plain = cipher.doFinal(ciphertext);
            } finally {
                java.util.Arrays.fill(chars, '\0');
                java.util.Arrays.fill(ciphertext, (byte) 0);
            }
            if (plain.length == 0 || plain.length > MAX_FILE_BYTES) throw new IllegalArgumentException("Decrypted archive size is invalid.");
            File output = new File(outputPath);
            File parent = output.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) throw new java.io.IOException("Cannot create output directory.");
            File temporary = new File(outputPath + ".tmp");
            try {
                Files.write(temporary.toPath(), plain);
                if (output.exists() && !output.delete()) throw new java.io.IOException("Cannot replace temporary archive.");
                if (!temporary.renameTo(output)) throw new java.io.IOException("Cannot finalize decrypted archive.");
            } finally {
                if (temporary.exists()) temporary.delete();
            }
            return output.getAbsolutePath();
        } finally {
            java.util.Arrays.fill(encoded, (byte) 0);
            if (plain != null) java.util.Arrays.fill(plain, (byte) 0);
        }
    }
}
